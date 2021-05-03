"Operation: Produce PDF file from a note and its subnotes."

import io
import json

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.rl_config import defaultPageSize

import flask

from operation import BaseOperation

PDF_MIMETYPE = "application/pdf"


class Operation(BaseOperation):
    "Produce PDF file from a note and its subnotes."

    title = "PDF file"

    def __init__(self, config):
        self.debug = config.get("DEBUG")

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
            "font_name": {
                "type": "select",
                "description": "The font to use for body text.",
                "values": ["Helvetica", "Times-Roman", "Courier"],
                "default": "Helvetica"
            },
            "line_spacing": {
                "type": "select",
                "description": "Spacing between lines of body text.",
                "values": [1, 1.5, 2],
                "default": 1
            },
        }

    def execute(self, note, form):
        """Execute the operation for the given note.
        The form is a dictionary containing the required parameters;
        typically 'flask.request.form'.
        Raise ValueError if something is wrong.
        Return True if the note was changed.
        If this operation generates a response, return it.
        Otherwise return None.
        """
        self.styles = getSampleStyleSheet()
        font_name = form.get("font_name")
        self.styles["BodyText"].fontSize = 11
        if font_name:
            self.styles["BodyText"].fontName = font_name
        self.line_spacing = form.get("line_spacing")
        if self.line_spacing:
            self.line_spacing = float(self.line_spacing)
            self.styles["BodyText"].leading = self.line_spacing * \
                                              self.styles["BodyText"].fontSize
        else:
            self.line_spacing = 1
        self.styles["BodyText"].leading *= 1.2
        if form.get("subnotes"):
            notes = list(note.traverse())
        else:
            note.level = 0
            notes = [note]
        self.items = [Spacer(1, 0.1 * self.line_spacing * cm)]
        for n in notes:
            self.items.append(Paragraph(n.title, self.styles["Title"]))
            self.items.append(Spacer(1, 0.1 * self.line_spacing * cm))
            self.content = ""
            for child in n.ast["children"]:
                self.render(child)
            self.flush()
        output = io.BytesIO()
        document = SimpleDocTemplate(output)
        document.build(self.items,
                       onFirstPage=self.page_number,
                       onLaterPages=self.page_number)
        response = flask.make_response(output.getvalue())
        response.headers.set("Content-Type", PDF_MIMETYPE)
        response.headers.set("Content-Disposition", "attachment",
                             filename=f"{note.title}.pdf")
        return response

    def render(self, child):
        "Output content of child recursively."
        if child["element"] == "paragraph":
            self.flush()
            for child2 in child["children"]:
                self.render(child2)
        elif child["element"] == "raw_text":
            self.content += child["children"]
        elif child["element"] == "emphasis":
            self.content += "<i>"
            for child2 in child["children"]:
                self.render(child2)
            self.content += "</i>"
        elif child["element"] == "strong_emphasis":
            self.content += "<b>"
            for child2 in child["children"]:
                self.render(child2)
            self.content += "</b>"
        elif child["element"] == "blank_line":
            self.flush()
            self.items.append(Spacer(1, 0.1 * self.line_spacing * cm))
        elif child["element"] == "heading":
            self.flush()
            for child2 in child["children"]:
                self.render(child2)
            self.items.append(
                Paragraph(self.content, self.styles[f"Heading{child['level']}"]))
            self.content = ""
        elif self.debug:
            print("child", json.dumps(child, indent=2))

    def flush(self):
        "If any content, then flush it out."
        if self.content:
            self.items.append(Paragraph(self.content, self.styles["BodyText"]))
            self.content = ""

    def page_number(self, canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 9)
        canvas.drawString(defaultPageSize[0] - 2 * cm, 2 * cm, f"{doc.page}")
        canvas.restoreState()
