from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QMainWindow, QTextEdit, QLabel, QLineEdit, QPushButton, QGridLayout, QWidget, QComboBox, QCheckBox, QProgressBar
from PyQt5.QtCore import Qt, QEvent
import sys
import json

from dataSource import load_config
from utils.ol import OUTORDER, REMOVE, format_ol, remove_keywords

CONFIG_FILE = load_config()

TEXTMAP_PATH = f'{CONFIG_FILE["RepoPath"]}/TextMap'
LANGS = ['CHS', 'CHT', 'DE', 'EN', 'ES', 'FR', 'ID', 'JP', 'KR', 'PT', 'RU', 'TH', 'VI', 'TR', 'IT']
data = {}


def print_progress_bar(iteration, total, length=50):
    percent = f"{100 * (iteration / float(total)):.1f}"
    filled_length = int(length * iteration // total)
    bar = '█' * filled_length + '-' * (length - filled_length)
    print(f'\rLoading OL: |{bar}| {percent}%', end='\r')
    if iteration == total: 
        print()


def load_data(progress_callback = None):
    for index, lang in enumerate(LANGS):
        with open(f'{TEXTMAP_PATH}/TextMap{lang}.json', 'r', encoding='utf-8') as file:
            data[lang] = json.load(file)
        if progress_callback:
            progress_callback(index + 1, len(LANGS))
        print_progress_bar(index + 1, len(LANGS))
            

def gen_ol(text, input_lang = 'EN', tl = True, rm = True):
    textid = 0

    for item, value in data[input_lang].items():
        if value == text:
            textid = item
            break

    if textid == 0:
        return 'Not found.'

    return format_ol({lang: values.get(textid) for lang, values in data.items()}, text, tl, rm)


class LoadingWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Loading")
        self.setGeometry(300, 300, 300, 100)
        
        layout = QGridLayout()
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMaximum(len(LANGS))
        layout.addWidget(self.progress_bar, 0, 0)
        
        self.setLayout(layout)

    def update_progress(self, value, total):
        self.progress_bar.setValue(value)


class OLGenApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("OL Gen")
        self.setGeometry(100, 100, 425, 650)
        
        font = QFont("Arial", 9)

        layout = QGridLayout()
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)
        layout.setColumnStretch(3, 1)

        # Dropdown menu for input language
        self.input_lang_label = QLabel("Input Language:")
        self.input_lang_label.setFont(font)
        layout.addWidget(self.input_lang_label, 0, 0)
        
        self.lang_dropdown = QComboBox(self)
        self.lang_dropdown.addItems(LANGS)
        self.lang_dropdown.setCurrentIndex(3)
        self.lang_dropdown.setFont(font)
        layout.addWidget(self.lang_dropdown, 0, 1)
        
        # Checkboxes for Translation and Romanization
        self.translation_checkbox = QCheckBox("Translation", self)
        self.translation_checkbox.setChecked(True)
        self.translation_checkbox.setFont(font)
        layout.addWidget(self.translation_checkbox, 0, 2)
        
        self.romanization_checkbox = QCheckBox("Romanization", self)
        self.romanization_checkbox.setChecked(True)
        self.romanization_checkbox.setFont(font)
        layout.addWidget(self.romanization_checkbox, 0, 3)

        self.entry = QLineEdit(self)
        self.entry.setFont(font)
        self.entry.installEventFilter(self)
        layout.addWidget(self.entry, 1, 0, 1, 4)

        self.generate_button = QPushButton("Generate", self)
        self.generate_button.setFont(font)
        self.generate_button.clicked.connect(self.on_generate)
        layout.addWidget(self.generate_button, 2, 0, 1, 4)

        self.output_text = QTextEdit(self)
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont("Consolas", 10))
        self.output_text.setStyleSheet('color: #80c; font-weight: bold;')
        layout.addWidget(self.output_text, 3, 0, 1, 4)
        
        self.copy_button = QPushButton("Copy", self)
        self.copy_button.setFont(font)
        self.copy_button.clicked.connect(self.copy_output)
        layout.addWidget(self.copy_button, 4, 0, 1, 4)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Show the loading window and load data
        self.show_loading_window()
        
    def eventFilter(self, obj, event):
        if obj == self.entry and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Return:
            self.on_generate()
            return True
        return super().eventFilter(obj, event)

    def show_loading_window(self):
        self.loading_window = LoadingWindow()
        self.loading_window.show()
        QApplication.processEvents()  # Ensure the loading window is displayed before loading

        load_data(progress_callback=self.loading_window.update_progress)

        self.loading_window.close()

    def on_generate(self):
        text = self.entry.text()
        output = gen_ol(text, self.lang_dropdown.currentText(), self.translation_checkbox.isChecked(), self.romanization_checkbox.isChecked())
        self.output_text.setText(output)
        
    def copy_output(self):
        self.output_text.selectAll()
        self.output_text.copy()


def main():
    app = QApplication(sys.argv)
    window = OLGenApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
