"Operation: Image OCR."

from operation import BaseOperation

import pytesseract


class Operation(BaseOperation):
    """Language-dependent Optical Character Recognition (OCR) on the image.
    The identified text is added to the note.
    """

    DEFAULT_TIMEOUT = 5.0
    EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif")

    def __init__(self, config):
        self.timeout = config.get("IMAGE_OCR_TIMEOUT") or self.DEFAULT_TIMEOUT
        if self.timeout < 0.0:
            raise ValueError("Invalid IMAGE_OCR_TIMEOUT value; must be positive.")
        self.languages = config.get("IMAGE_OCR_LANGUAGES")
        if not self.languages:
            self.languages = pytesseract.get_languages()
            try:
                self.languages.remove("osd")
            except ValueError:
                pass
        if not self.languages:
            raise ValueError("No languages available for pytesseract.")

    @property
    def title(self):
        return "Image OCR"

    def is_relevant(self, note):
        "Is this operation relevant for the given note?"
        if not note.file_extension:
            return False
        return note.file_extension in self.EXTENSIONS

    def get_parameters(self, note):
        "Return the parameters required to control the operation."
        return {
            "lang": {
                "type": "select",
                "description": "Language used for character recognition.",
                "values": self.languages,
            }
        }

    def execute(self, note, form):
        """Execute the operation for the given note. The form is a dictionary
        containin the required parameters; typically 'flask.request.form'.
        Raise ValueError if something is wrong.
        """
        lang = form.get("lang")
        if not lang:
            raise ValueError("No 'lang' parameter provided.")
        if lang not in self.languages:
            raise ValueError(f"Unknown 'lang' parameter value: '{lang}'.")
        try:
            text = pytesseract.image_to_string(
                note.abspathfile, lang=lang, timeout=self.timeout
            )
            text = text.strip()
            if not text:
                return
        except RuntimeError:
            raise ValueError("pytesseract timeout.")
        if note.text:
            note.text = note.text + "\n\n" + text
        else:
            note.text = text
