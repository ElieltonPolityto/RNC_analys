from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QThread, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
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


DIALOG_STYLESHEET = """
QMessageBox, QDialog {
    background: #f8fafc;
}
QLabel {
    color: #111827;
    background: transparent;
}
QPushButton {
    background: #ffffff;
    color: #111827;
    border: 1px solid #8da0b7;
    padding: 7px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background: #eef5ff;
}
"""


class TaskThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)
    progress_changed = Signal(int, str)

    def __init__(self, fn: Callable[..., Any], *, with_progress: bool = False) -> None:
        super().__init__()
        self.fn = fn
        self.with_progress = with_progress

    def run(self) -> None:
        try:
            if self.with_progress:
                self.succeeded.emit(self.fn(self.emit_progress))
            else:
                self.succeeded.emit(self.fn())
        except Exception as exc:
            self.failed.emit(str(exc))

    def emit_progress(self, percent: int, message: str) -> None:
        self.progress_changed.emit(max(0, min(100, percent)), message)


class RncAnalystWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.context = service.create_context(BASE_DIR)
        self.loaded_pdf: service.PdfLoadResult | None = None
        self.analysis_result: service.AnalysisResult | None = None
        self.active_tasks: list[TaskThread] = []
        self.last_progress_percent = 0
        self.last_progress_message = ""
        self.ai_progress_timer = QTimer(self)
        self.ai_progress_timer.setInterval(900)
        self.ai_progress_timer.timeout.connect(self.advance_ai_progress)

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
        page.setObjectName("Page")
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.setContentsMargins(22, 18, 22, 18)

        title = QLabel("Nova analise")
        title.setObjectName("Title")
        layout.addWidget(title)

        self.mode_label = QLabel(service.ai_mode_label())
        self.mode_label.setObjectName("StatusPill")
        layout.addWidget(self.mode_label)

        layout.addWidget(self.section_label("1. Projeto"))
        file_row = QHBoxLayout()
        self.select_pdf_button = QPushButton("Selecionar PDF")
        self.select_pdf_button.setObjectName("PrimaryButton")
        self.select_pdf_button.clicked.connect(self.select_pdf)
        self.file_label = QLabel("Nenhum PDF selecionado.")
        self.file_label.setObjectName("InfoBox")
        self.file_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        file_row.addWidget(self.select_pdf_button)
        file_row.addWidget(self.file_label, stretch=1)
        layout.addLayout(file_row)

        layout.addWidget(self.section_label("2. Leitura automatica"))
        self.status_label = QLabel("Selecione um PDF para iniciar.")
        self.status_label.setObjectName("StatusBox")
        layout.addWidget(self.status_label)

        self.detected_label = QLabel("Dados detectados: aguardando PDF.")
        self.detected_label.setObjectName("InfoBox")
        self.detected_label.setWordWrap(True)
        layout.addWidget(self.detected_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        layout.addWidget(self.section_label("3. Analise"))
        action_row = QHBoxLayout()
        self.analyze_button = QPushButton("Analisar projeto")
        self.analyze_button.setObjectName("PrimaryButton")
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

        layout.addWidget(self.section_label("4. Relatorio"))
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setPlaceholderText("O resultado da analise aparecera aqui.")
        layout.addWidget(self.result_text, stretch=1)

        self.tabs.addTab(page, "Nova analise")

    def section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        return label

    def build_history_tab(self) -> None:
        page = QWidget()
        page.setObjectName("Page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 22, 18)
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
        page.setObjectName("Page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 22, 18)
        self.case_status_label = QLabel("Base RNC: verificando...")
        self.case_status_label.setObjectName("StatusBox")
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
        page.setObjectName("Page")
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.setContentsMargins(22, 18, 22, 18)
        self.settings_label = QLabel(self.settings_text())
        self.settings_label.setObjectName("InfoBox")
        self.settings_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.settings_label)

        model_row = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(["gpt-5-mini", "gpt-5", "gpt-5.1", "gpt-5.2"])
        self.model_combo.setCurrentText(service.openai_model())
        self.save_model_button = QPushButton("Salvar modelo de IA")
        self.save_model_button.setObjectName("PrimaryButton")
        self.save_model_button.clicked.connect(self.confirm_save_model)
        model_row.addWidget(QLabel("Modelo OpenAI"))
        model_row.addWidget(self.model_combo, stretch=1)
        model_row.addWidget(self.save_model_button)
        layout.addLayout(model_row)
        model_help = QLabel("gpt-5-mini reduz custo. Use modelos maiores apenas quando precisar de revisao mais profunda.")
        model_help.setObjectName("Hint")
        model_help.setWordWrap(True)
        layout.addWidget(model_help)

        layout.addWidget(self.section_label("Prompt efetivo da proxima analise"))
        prompt_preview_row = QHBoxLayout()
        self.prompt_preview_button = QPushButton("Ver prompt da proxima analise")
        self.prompt_preview_button.clicked.connect(self.show_effective_prompt)
        prompt_preview_row.addWidget(self.prompt_preview_button)
        prompt_preview_row.addStretch(1)
        layout.addLayout(prompt_preview_row)
        preview_help = QLabel("Mostra exatamente o SYSTEM e o USER prompt que serao enviados para o modelo, usando o prompt base salvo.")
        preview_help.setObjectName("Hint")
        preview_help.setWordWrap(True)
        layout.addWidget(preview_help)
        self.effective_prompt_preview = QPlainTextEdit()
        self.effective_prompt_preview.setReadOnly(True)
        self.effective_prompt_preview.setPlaceholderText("Selecione um PDF na aba Nova analise e clique em Ver prompt da proxima analise.")
        self.effective_prompt_preview.setMinimumHeight(180)
        layout.addWidget(self.effective_prompt_preview, stretch=1)

        layout.addWidget(self.section_label("Prompt base editavel"))
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
        self.set_progress(0, "Preparando analise")
        self.analyze_button.setEnabled(False)
        self.run_task(
            lambda progress: service.run_analysis(self.context, self.loaded_pdf, progress=progress),
            self.on_analysis_done,
            self.on_task_error,
            with_progress=True,
        )

    def on_analysis_done(self, result: service.AnalysisResult) -> None:
        self.analysis_result = result
        self.stop_ai_progress()
        status = result.result.get("status", "")
        provider_error = result.result.get("provider_error", "")
        if status == "erro_provedor":
            self.set_progress(100, "Pre-analise local concluida; IA externa indisponivel")
        else:
            self.set_progress(100, "Analise concluida")
        self.analyze_button.setEnabled(True)
        self.set_report_buttons(True)
        lines = [
            f"Analise registrada com ID {result.analysis_id}.",
            f"Status: {status}",
            f"Resumo: {result.result.get('summary', '')}",
        ]
        if provider_error:
            lines.extend(["", f"Aviso da API: {provider_error}"])
        lines.extend(["", "Relatorio PDF gerado e aberto automaticamente."])
        self.result_text.setPlainText("\n".join(lines))
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
        self.show_info(
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
        self.show_info("Prompt salvo", f"Prompt salvo. Hash: {digest}")

    def confirm_save_model(self) -> None:
        model = self.model_combo.currentText().strip()
        if not model:
            self.show_warning("Modelo invalido", "Informe um modelo OpenAI valido.")
            return
        normalized = service.save_openai_model(BASE_DIR, model)
        self.model_combo.setCurrentText(normalized)
        self.mode_label.setText(service.ai_mode_label())
        self.settings_label.setText(self.settings_text())
        self.show_info(
            "Modelo salvo",
            f"Modelo OpenAI salvo como {normalized}.\nA proxima analise ja usara essa configuracao.",
        )

    def show_effective_prompt(self) -> None:
        if self.loaded_pdf is None:
            self.show_warning(
                "Prompt efetivo",
                "Selecione um PDF na aba Nova analise para montar o prompt efetivo da proxima analise.",
            )
            return
        try:
            prompt = service.build_effective_prompt(self.context, self.loaded_pdf)
        except Exception as exc:
            self.show_warning("Prompt efetivo", f"Nao foi possivel montar o prompt efetivo.\n\n{exc}")
            return
        self.effective_prompt_preview.setPlainText(prompt)
        self.tabs.setCurrentWidget(self.effective_prompt_preview.parentWidget())

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
            self.show_warning("Arquivo nao encontrado", f"Nao foi possivel abrir:\n{path}")
            return
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def run_task(
        self,
        fn: Callable[..., Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[str], None],
        *,
        with_progress: bool = False,
    ) -> None:
        thread = TaskThread(fn, with_progress=with_progress)
        self.active_tasks.append(thread)
        thread.succeeded.connect(on_success)
        thread.failed.connect(on_error)
        thread.progress_changed.connect(self.on_progress_changed)
        thread.finished.connect(lambda: self.task_finished(thread))
        thread.start()

    def task_finished(self, thread: TaskThread) -> None:
        if thread in self.active_tasks:
            self.active_tasks.remove(thread)

    def on_task_error(self, message: str) -> None:
        self.stop_ai_progress()
        self.status_label.setText(f"{self.last_progress_message or 'Falha na operacao'} - erro")
        self.progress.setVisible(self.last_progress_percent > 0)
        self.analyze_button.setEnabled(self.loaded_pdf is not None)
        self.show_warning("RNC Analyst", f"{message}\n\nConfira o arquivo e tente novamente.")

    def on_progress_changed(self, percent: int, message: str) -> None:
        self.set_progress(percent, message)
        if 50 <= percent < 80:
            self.start_ai_progress()
        else:
            self.stop_ai_progress()

    def set_progress(self, percent: int, message: str) -> None:
        self.last_progress_percent = max(0, min(100, percent))
        self.last_progress_message = message
        self.status_label.setText(f"{message}... {self.last_progress_percent}%")
        self.progress.setRange(0, 100)
        self.progress.setValue(self.last_progress_percent)
        self.progress.setFormat(f"{self.last_progress_percent}%")
        self.progress.setVisible(True)

    def start_ai_progress(self) -> None:
        if not self.ai_progress_timer.isActive():
            self.ai_progress_timer.start()

    def stop_ai_progress(self) -> None:
        if self.ai_progress_timer.isActive():
            self.ai_progress_timer.stop()

    def advance_ai_progress(self) -> None:
        if self.last_progress_percent < 79:
            self.set_progress(self.last_progress_percent + 1, self.last_progress_message or "Executando analise")

    def set_busy(self, message: str) -> None:
        self.status_label.setText(message)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("0%")
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
        box = self.build_message_box(QMessageBox.Question, "Confirmar", message)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        return box.exec() == QMessageBox.Yes

    def show_info(self, title: str, message: str) -> None:
        self.build_message_box(QMessageBox.Information, title, message).exec()

    def show_warning(self, title: str, message: str) -> None:
        self.build_message_box(QMessageBox.Warning, title, message).exec()

    def build_message_box(self, icon: QMessageBox.Icon, title: str, message: str) -> QMessageBox:
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(message)
        box.setStyleSheet(DIALOG_STYLESHEET)
        return box

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
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#eef2f7"))
    palette.setColor(QPalette.WindowText, QColor("#111827"))
    palette.setColor(QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.AlternateBase, QColor("#f1f5f9"))
    palette.setColor(QPalette.Text, QColor("#111827"))
    palette.setColor(QPalette.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ButtonText, QColor("#111827"))
    palette.setColor(QPalette.Highlight, QColor("#b9daf7"))
    palette.setColor(QPalette.HighlightedText, QColor("#0f172a"))
    palette.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipText, QColor("#111827"))
    app.setPalette(palette)
    app.setStyleSheet(
        """
        * {
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 10.5pt;
            color: #111827;
        }
        QWidget, QDialog, QMessageBox, QFileDialog, QMainWindow, QTabWidget::pane {
            background: #eef2f7;
            color: #111827;
        }
        QWidget#Page {
            background: #eef2f7;
        }
        QLabel {
            background: transparent;
            color: #111827;
        }
        QTabBar::tab {
            background: #dde5ef;
            color: #1f2937;
            padding: 9px 16px;
            border: 1px solid #b8c4d3;
            border-bottom: none;
            margin-right: 3px;
            font-weight: 600;
        }
        QTabBar::tab:selected {
            background: #ffffff;
            color: #0f172a;
        }
        QLabel#Title {
            font-size: 23px;
            font-weight: 750;
            color: #0f172a;
        }
        QLabel#SectionTitle {
            color: #0f172a;
            font-size: 14px;
            font-weight: 750;
            padding-top: 8px;
        }
        QLabel#Hint {
            color: #475569;
            font-size: 9.5pt;
        }
        QLabel#StatusPill {
            background: #d9f0e8;
            color: #064e3b;
            border: 1px solid #9ccfbd;
            padding: 7px 10px;
            font-weight: 700;
        }
        QLabel#StatusBox, QLabel#InfoBox {
            background: #ffffff;
            border: 1px solid #b8c4d3;
            padding: 9px 10px;
            color: #111827;
        }
        QPushButton {
            background: #ffffff;
            color: #111827;
            border: 1px solid #8da0b7;
            padding: 8px 13px;
            font-weight: 600;
        }
        QPushButton:hover {
            background: #f4f7fb;
            border-color: #52657d;
        }
        QPushButton:disabled {
            background: #d7dde6;
            color: #687386;
            border-color: #b8c4d3;
        }
        QPushButton#PrimaryButton {
            background: #1769aa;
            color: #ffffff;
            border: 1px solid #0f4f82;
        }
        QPushButton#PrimaryButton:hover {
            background: #12578e;
        }
        QComboBox {
            background: #ffffff;
            color: #111827;
            border: 1px solid #8da0b7;
            padding: 7px 9px;
            min-height: 22px;
        }
        QComboBox QAbstractItemView {
            background: #ffffff;
            color: #111827;
            border: 1px solid #8da0b7;
            selection-background-color: #dbeafe;
            selection-color: #0f172a;
        }
        QLineEdit, QTextEdit, QPlainTextEdit, QTableWidget, QTableView, QListView {
            background: #ffffff;
            color: #111827;
            border: 1px solid #b8c4d3;
            selection-background-color: #b9daf7;
            selection-color: #0f172a;
        }
        QHeaderView::section {
            background: #d7e1ee;
            color: #111827;
            padding: 7px;
            border: 1px solid #b8c4d3;
            font-weight: 700;
        }
        QProgressBar {
            border: 1px solid #8da0b7;
            background: #ffffff;
            min-height: 14px;
        }
        QProgressBar::chunk {
            background: #1769aa;
        }
        QCheckBox {
            color: #111827;
            background: transparent;
            spacing: 7px;
        }
        QMenu {
            background: #ffffff;
            color: #111827;
            border: 1px solid #8da0b7;
        }
        QMenu::item:selected {
            background: #dbeafe;
            color: #0f172a;
        }
        QToolTip {
            background: #ffffff;
            color: #111827;
            border: 1px solid #8da0b7;
            padding: 5px;
        }
        QScrollBar:vertical, QScrollBar:horizontal {
            background: #edf2f7;
            border: 1px solid #cbd5e1;
        }
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
            background: #94a3b8;
            min-height: 24px;
            min-width: 24px;
        }
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
