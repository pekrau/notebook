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
                self.languages.remove("ods")
            except ValueError:
                pass

    @property
    def name(self):
        return "Image OCR"

    def is_relevant(self, note):
        "Is this operation relevant for the given note?"
        if not note.file_extension: return False
        return note.file_extension in [".png", ".jpg", ".jpeg", ".gif"]

    def get_parameters(self, note):
        "Return the parameters required to control the operation."
        return {"language": {
            "type": "select",
            "values": 

    def execute(self, note):
        "Execute the operation for the given note."
        
