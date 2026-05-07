from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QUrl

from src import desktop_service as service


BASE_DIR = Path(__file__).resolve().parent


class TaskThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self.fn = fn

    def run(self) -> None:
        try:
            self.succeeded.emit(self.fn())
        except Exception as exc:
            self.failed.emit(str(exc))


class RncAnalystWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.context = service.create_context(BASE_DIR)
        self.loaded_pdf: service.PdfLoadResult | None = None
        self.analysis_result: service.AnalysisResult | None = None
        self.active_tasks: list[TaskThread] = []

        self.setWindowTitle("RNC Analyst")
        self.resize(1120, 760)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.build_new_analysis_tab()
        self.build_history_tab()
        self.build_case_base_tab()
        self.build_settings_tab()
        self.refresh_history()
        self.refresh_case_base()
        self.start_background_index()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown_tasks)

    def build_new_analysis_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        title = QLabel("Nova analise")
        title.setObjectName("Title")
        layout.addWidget(title)

        self.mode_label = QLabel(service.ai_mode_label())
        self.mode_label.setObjectName("StatusPill")
        layout.addWidget(self.mode_label)

        file_row = QHBoxLayout()
        self.select_pdf_button = QPushButton("Selecionar PDF")
        self.select_pdf_button.clicked.connect(self.select_pdf)
        self.file_label = QLabel("Nenhum PDF selecionado.")
        self.file_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        file_row.addWidget(self.select_pdf_button)
        file_row.addWidget(self.file_label, stretch=1)
        layout.addLayout(file_row)

        self.status_label = QLabel("Selecione um PDF para iniciar.")
        layout.addWidget(self.status_label)

        self.detected_label = QLabel("Dados detectados: aguardando PDF.")
        self.detected_label.setWordWrap(True)
        layout.addWidget(self.detected_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        action_row = QHBoxLayout()
        self.analyze_button = QPushButton("Analisar projeto")
        self.analyze_button.setEnabled(False)
        self.analyze_button.clicked.connect(self.analyze_project)
        self.open_pdf_button = QPushButton("Abrir PDF")
        self.open_pdf_button.setEnabled(False)
        self.open_pdf_button.clicked.connect(lambda: self.open_report("pdf"))
        self.open_xlsx_button = QPushButton("Abrir Excel")
        self.open_xlsx_button.setEnabled(False)
        self.open_xlsx_button.clicked.connect(lambda: self.open_report("xlsx"))
        self.open_folder_button = QPushButton("Abrir pasta")
        self.open_folder_button.setEnabled(False)
        self.open_folder_button.clicked.connect(self.open_reports_folder)
        action_row.addWidget(self.analyze_button)
        action_row.addWidget(self.open_pdf_button)
        action_row.addWidget(self.open_xlsx_button)
        action_row.addWidget(self.open_folder_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setPlaceholderText("O resultado da analise aparecera aqui.")
        layout.addWidget(self.result_text, stretch=1)

        self.tabs.addTab(page, "Nova analise")

    def build_history_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        refresh = QPushButton("Atualizar historico")
        refresh.clicked.connect(self.refresh_history)
        row.addWidget(refresh)
        row.addStretch(1)
        layout.addLayout(row)
        self.history_table = QTableWidget(0, 8)
        self.history_table.setHorizontalHeaderLabels(
            ["ID", "Data", "Arquivo", "Cliente", "Documento", "Status", "PDF", "Excel"]
        )
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.history_table.cellDoubleClicked.connect(self.open_history_file)
        layout.addWidget(self.history_table)
        self.tabs.addTab(page, "Historico")

    def build_case_base_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.case_status_label = QLabel("Base RNC: verificando...")
        layout.addWidget(self.case_status_label)
        row = QHBoxLayout()
        reindex = QPushButton("Reindexar base")
        reindex.clicked.connect(self.confirm_reindex)
        self.fill_metadata_check = QCheckBox("Preencher campos vazios em metadata.json existentes")
        self.fill_metadata_check.setChecked(True)
        metadata = QPushButton("Gerar metadados e reindexar")
        metadata.clicked.connect(self.confirm_metadata)
        row.addWidget(reindex)
        row.addWidget(metadata)
        row.addWidget(self.fill_metadata_check)
        row.addStretch(1)
        layout.addLayout(row)
        self.case_table = QTableWidget(0, 3)
        self.case_table.setHorizontalHeaderLabels(["Caso", "Status", "Pasta"])
        self.case_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.case_table)
        self.tabs.addTab(page, "Base RNC")

    def build_settings_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.settings_label = QLabel(self.settings_text())
        self.settings_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.settings_label)
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlainText(service.load_prompt(self.context))
        layout.addWidget(self.prompt_edit, stretch=1)
        save_prompt = QPushButton("Salvar prompt")
        save_prompt.clicked.connect(self.confirm_save_prompt)
        layout.addWidget(save_prompt)
        self.tabs.addTab(page, "Configuracoes")

    def settings_text(self) -> str:
        model = service.openai_model()
        api_state = "configurada" if os.getenv("OPENAI_API_KEY", "").strip() else "nao configurada"
        return "\n".join(
            [
                f"{service.ai_mode_label()} ({model})",
                f"OPENAI_API_KEY: {api_state}",
                f"Banco SQLite: {self.context.db_path}",
                f"Relatorios: {self.context.runtime_dirs['reports']}",
                f"Base RNC: {self.context.case_base_paths['knowledge_base']}",
            ]
        )

    def select_pdf(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(self, "Selecionar PDF", str(BASE_DIR), "PDF (*.pdf)")
        if not file_name:
            return
        path = Path(file_name)
        self.set_busy("Lendo PDF...")
        self.run_task(lambda: service.load_pdf(path), self.on_pdf_loaded, self.on_task_error)

    def on_pdf_loaded(self, loaded: service.PdfLoadResult) -> None:
        self.loaded_pdf = loaded
        self.analysis_result = None
        self.set_idle()
        self.file_label.setText(str(loaded.path))
        pages = loaded.summary.get("pages_count", 0)
        critical = len(loaded.summary.get("critical_pages", []))
        self.status_label.setText(f"PDF valido. {pages} paginas, {critical} paginas criticas detectadas.")
        inferred = loaded.summary.get("inferred", {})
        self.detected_label.setText(
            "Dados detectados: "
            f"cliente={inferred.get('cliente') or 'nao identificado'} | "
            f"documento={inferred.get('documento') or 'nao identificado'} | "
            f"pedido={inferred.get('pedido') or 'nao identificado'} | "
            f"projeto={inferred.get('projeto') or 'nao identificado'} | "
            f"revisao={inferred.get('revisao') or 'nao identificado'}"
        )
        self.analyze_button.setEnabled(True)
        self.set_report_buttons(False)
        self.result_text.clear()

    def analyze_project(self) -> None:
        if self.loaded_pdf is None:
            return
        self.set_busy("Executando analise...")
        self.analyze_button.setEnabled(False)
        self.run_task(lambda: service.run_analysis(self.context, self.loaded_pdf), self.on_analysis_done, self.on_task_error)

    def on_analysis_done(self, result: service.AnalysisResult) -> None:
        self.analysis_result = result
        self.set_idle()
        self.analyze_button.setEnabled(True)
        self.set_report_buttons(True)
        self.result_text.setPlainText(
            "\n".join(
                [
                    f"Analise registrada com ID {result.analysis_id}.",
                    f"Status: {result.result.get('status', '')}",
                    f"Resumo: {result.result.get('summary', '')}",
                    "",
                    "Relatorio PDF gerado e aberto automaticamente.",
                ]
            )
        )
        self.refresh_history()
        self.open_report("pdf")

    def start_background_index(self) -> None:
        self.case_status_label.setText("Base RNC: verificando em segundo plano...")
        self.run_task(lambda: service.index_case_base(self.context), self.on_index_done, self.on_index_error)

    def on_index_done(self, result: dict[str, Any]) -> None:
        self.case_status_label.setText(
            "Base RNC: "
            f"{result.get('ok', 0)} ok, {result.get('warning', 0)} alerta, "
            f"{result.get('error', 0)} erro, {result.get('pruned', 0)} removido."
        )
        self.refresh_case_base()

    def on_index_error(self, message: str) -> None:
        self.case_status_label.setText(f"Base RNC: falha na indexacao. {message}")

    def confirm_reindex(self) -> None:
        if self.ask_confirm("Reindexar a base RNC agora?"):
            self.set_busy("Reindexando base RNC...")
            self.run_task(lambda: service.index_case_base(self.context), self.on_index_done, self.on_task_error)

    def confirm_metadata(self) -> None:
        if self.ask_confirm("Gerar metadados e reindexar a base RNC agora?"):
            fill = self.fill_metadata_check.isChecked()
            self.set_busy("Gerando metadados...")
            self.run_task(lambda: service.generate_metadata_and_reindex(self.context, fill), self.on_metadata_done, self.on_task_error)

    def on_metadata_done(self, result: dict[str, Any]) -> None:
        self.set_idle()
        metadata = result.get("metadata", {})
        QMessageBox.information(
            self,
            "Metadados",
            "Metadados processados: "
            f"{metadata.get('created', 0)} criados, {metadata.get('updated', 0)} atualizados, "
            f"{metadata.get('skipped', 0)} ignorados, {metadata.get('error', 0)} erro(s).",
        )
        self.on_index_done(result.get("index", {}))

    def confirm_save_prompt(self) -> None:
        if not self.ask_confirm("Salvar alteracoes no prompt base?"):
            return
        digest = service.save_prompt(self.context, self.prompt_edit.toPlainText())
        QMessageBox.information(self, "Prompt salvo", f"Prompt salvo. Hash: {digest}")

    def refresh_history(self) -> None:
        rows = service.history_rows(self.context)
        self.history_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row.get("id", ""),
                row.get("created_at", ""),
                row.get("pdf_name", ""),
                row.get("customer", ""),
                row.get("document", ""),
                row.get("status", ""),
                row.get("report_pdf_path", ""),
                row.get("report_xlsx_path", ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                self.history_table.setItem(row_index, column, item)

    def refresh_case_base(self) -> None:
        overview = service.case_base_overview(self.context)
        indexed_by_id = {row.get("case_id"): row for row in overview["indexed_cases"]}
        case_dirs = overview["case_dirs"]
        self.case_table.setRowCount(len(case_dirs))
        for row_index, path in enumerate(case_dirs):
            indexed = indexed_by_id.get(path.name, {})
            values = [path.name, indexed.get("status", "nao indexado"), str(path)]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                self.case_table.setItem(row_index, column, item)

    def open_history_file(self, row: int, column: int) -> None:
        if column not in {6, 7}:
            return
        item = self.history_table.item(row, column)
        if item:
            self.open_path(Path(item.text()))

    def open_report(self, kind: str) -> None:
        if self.analysis_result is None:
            return
        path = self.analysis_result.report_paths.get(kind)
        if path:
            self.open_path(path)

    def open_reports_folder(self) -> None:
        if self.analysis_result is not None:
            self.open_path(self.analysis_result.report_paths["pdf"].parent)
        else:
            self.open_path(self.context.runtime_dirs["reports"])

    def open_path(self, path: Path) -> None:
        if not path.exists():
            QMessageBox.warning(self, "Arquivo nao encontrado", f"Nao foi possivel abrir:\n{path}")
            return
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def run_task(
        self,
        fn: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[str], None],
    ) -> None:
        thread = TaskThread(fn)
        self.active_tasks.append(thread)
        thread.succeeded.connect(on_success)
        thread.failed.connect(on_error)
        thread.finished.connect(lambda: self.task_finished(thread))
        thread.start()

    def task_finished(self, thread: TaskThread) -> None:
        if thread in self.active_tasks:
            self.active_tasks.remove(thread)

    def on_task_error(self, message: str) -> None:
        self.set_idle()
        self.analyze_button.setEnabled(self.loaded_pdf is not None)
        QMessageBox.warning(self, "RNC Analyst", message)

    def set_busy(self, message: str) -> None:
        self.status_label.setText(message)
        self.progress.setRange(0, 0)
        self.progress.setVisible(True)
        self.select_pdf_button.setEnabled(False)

    def set_idle(self) -> None:
        self.progress.setVisible(False)
        self.progress.setRange(0, 1)
        self.select_pdf_button.setEnabled(True)

    def set_report_buttons(self, enabled: bool) -> None:
        self.open_pdf_button.setEnabled(enabled)
        self.open_xlsx_button.setEnabled(enabled)
        self.open_folder_button.setEnabled(enabled)

    def ask_confirm(self, message: str) -> bool:
        return (
            QMessageBox.question(self, "Confirmar", message, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            == QMessageBox.Yes
        )

    def closeEvent(self, event: Any) -> None:
        if any(task.isRunning() for task in self.active_tasks):
            if not self.ask_confirm("Existe uma tarefa em andamento. Deseja fechar mesmo assim?"):
                event.ignore()
                return
            self.shutdown_tasks()
        event.accept()

    def shutdown_tasks(self) -> None:
        for task in list(self.active_tasks):
            if not task.isRunning():
                continue
            task.requestInterruption()
            if not task.wait(2000):
                task.terminate()
                task.wait(1000)


def apply_style(app: QApplication) -> None:
    app.setStyleSheet(
        """
        QMainWindow { background: #f7f8fa; }
        QLabel#Title { font-size: 22px; font-weight: 700; color: #1f2937; }
        QLabel#StatusPill { color: #0f766e; font-weight: 600; padding: 4px 0; }
        QPushButton { padding: 8px 12px; }
        QTextEdit, QPlainTextEdit, QTableWidget { background: white; border: 1px solid #d1d5db; }
        """
    )


def main() -> int:
    app = QApplication(sys.argv)
    apply_style(app)
    window = RncAnalystWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
