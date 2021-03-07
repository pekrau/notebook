"Operation: Perform Optical Character Recognition (OCR) on image files."

import pytesseract


DEFAULT_TIMEOUT = 5.0


class Operation:

    def __init__(self, config):
        self.timeout = config.get("IMAGE_OCR_TIMEOUT") or DEFAULT_TIMEOUT
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
    def name(self):
        return "Image OCR"

    @property
    def description(self):
        return "Language-dependent Optical Character Recognition of the image; add text to the note."

    def is_relevant(self, note):
        "Is this operation relevant for the given note?"
        if not note.file_extension: return False
        return note.file_extension in [".png", ".jpg", ".jpeg", ".gif"]

    def get_parameters(self, note):
        "Return the parameters required to control the operation."
        return {"lang": {"type": "select",
                         "description": "Language used for character recognition.",
                         "values": self.languages}}

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
            text = pytesseract.image_to_string(self.abspathfile,
                                               lang=lang,
                                               timeout=config["OCR_TIMEOUT"])
            text = text.strip()
            if not text: return
        except RuntimeError:
            raise ValueError("pytesseract timeout.")
        if note.text:
            note.text = note.text + "\n\n" + text
        else:
            note.text = text
