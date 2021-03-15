"Operation: Extract image file EXIF tags."

from operation import BaseOperation

import PIL
import PIL.ExifTags


class Operation(BaseOperation):
    "Extract EXIF tags from the image file."

    EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif")

    @property
    def title(self):
        return "Extract EXIF tags"

    def is_applicable(self, note):
        "Is this operation applicable to the given note?"
        if not note.file_extension:
            return False
        return note.file_extension in self.EXTENSIONS

    def get_parameters(self, note):
        "Return the parameters required to control the operation."
        return {
            "newline": {
                "type": "checkbox",
                "description": "Control output of tag-derived attributes.",
                "label": "Each attribute on its own line."
            }
        }

    def execute(self, note, form):
        """Execute the operation for the given note.
        The form is a dictionary containin the required parameters;
        typically 'flask.request.form'.
        Raise ValueError if something is wrong.
        Return True if the note was changed, otherwise None.
        """
        img = PIL.Image.open(note.abspathfile)
        exif = img._getexif()
        if not exif:
            return
        result = dict([(PIL.ExifTags.TAGS[k], v)
                       for k, v in exif.items()
                       if k in PIL.ExifTags.TAGS])
        attributes = [f"{{{tag}: {value}}}"
                      for tag, value in sorted(result.items())]
        if form.get("newline"):
            joiner = "  \n"
        else:
            joiner = "\n"
        attributes = joiner.join(attributes)
        if note.text:
            note.text = note.text + "\n\n" + attributes
        else:
            note.text = attributes
        return True
