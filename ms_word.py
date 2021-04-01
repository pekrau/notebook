"Operation: Produce MS Word file (docx) from a note and its subnotes."

import io
import json

import docx
import flask

from operation import BaseOperation

DOCX_MIMETYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

class Operation(BaseOperation):
    "Produce MS Word file (docx) from a note and its subnotes."

    title = "MS Word file"

    def is_applicable(self, note):
        "Is this operation applicable to the given note?"
        return True

    def get_parameters(self, note):
        "Return the parameters required to control the operation."
        return {
            "subnotes": {
                "type": "checkbox",
                "description": "Include text from subnotes.",
                "label": "Include subnotes.",
                "default": True
            },
            "font": {
                "type": "select",
                "description": "The font to use for running text.",
                "values": ["Arial", "New Times Roman", "Calibri"],
                "default": "Arial"
            }
        }

    def execute(self, note, form):
        """Execute the operation for the given note.
        The form is a dictionary containin the required parameters;
        typically 'flask.request.form'.
        Raise ValueError if something is wrong.
        Return True if the note was changed.
        If this operation generates a response, return it.
        Otherwise return None.
        """
        document = docx.Document()
        font = form.get("font")
        if font:
            document.styles["Normal"].font.name = font
        if form.get("subnotes"):
            notes = list(note.traverse())
        else:
            note.level = 0
            notes = [note]
        for n in notes:
            document.add_heading(n.title, n.level)
            for child in n.ast["children"]:
                self.render(document, child)
        output = io.BytesIO()
        document.save(output)
        response = flask.make_response(output.getvalue())
        response.headers.set("Content-Type", DOCX_MIMETYPE)
        response.headers.set("Content-Disposition", "attachment",
                             filename=f"{note.title}.docx")
        return response

    def render(self, document, child):
        if child["element"] == "paragraph":
            self.paragraph = document.add_paragraph()
            self.run = self.paragraph.add_run()
            for child2 in child["children"]:
                self.render(document, child2)
        elif child["element"] == "raw_text":
            self.run.add_text(child["children"])
        elif child["element"] == "emphasis":
            self.run = self.paragraph.add_run()
            self.run.italic = True
            for child2 in child["children"]:
                self.render(document, child2)
            self.run = self.paragraph.add_run()
        elif child["element"] == "strong_emphasis":
            self.run = self.paragraph.add_run()
            self.run.bold = True
            for child2 in child["children"]:
                self.render(document, child2)
            self.run = self.paragraph.add_run()
        else:
            print("child", json.dumps(child, indent=2))
