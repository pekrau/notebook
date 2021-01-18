"Simple app for personal notes. Optionally publish using GitHub pages."

__version__ = "0.2.0"

import copy as copy_module
import json
import os
# import shutil
# import urllib.parse

import flask
import marko
import jinja2.utils


SETTINGS = dict(VERSION=__version__,
                SERVER_NAME="127.0.0.1:5099",
                SECRET_KEY="this is a secret",
                TEMPLATES_AUTO_RELOAD=True,
                DEBUG=True,
                JSON_AS_ASCII=False,
                NOTES_ROOT="notes")

NOTE = None
LOOKUP = dict()


class Note:
    "Note and its subnotes, if any."

    def __init__(self, parent, title):
        self.parent = parent
        self.title = title
        self.text = ""
        self.subnotes = []

    @property
    def path(self):
        "Return the path of the note."
        if self.parent:
            assert self.title
            return os.path.join(self.parent, self.title)
        else:
            return self.title or ""

    @property
    def idpath(self):
        "Return the path of the note as a valid HTML code identifier."
        return self.path.replace("/", "-").replace(" ", "_").replace(",", "_")

    @property
    def abspath(self):
        "Return the absolute filepath of the note."
        path = self.path
        if path:
            return  os.path.join(SETTINGS["NOTES_ROOT"], path)
        else:
            return SETTINGS["NOTES_ROOT"]

    @property
    def parents(self):
        "Return a list of parents and their paths."
        result = []
        path = os.path.dirname(self.path)
        while path:
            parent, title = os.path.split(path)
            result.append((title, path))
            path = parent
        return reversed(result)

    @property
    def count(self):
        return len(self.subnotes)

    def read(self):
        "Read this note and its subnotes from disk."
        abspath = self.abspath
        if os.path.exists(abspath):
            # It's a directory with subnotes.
            try:
                with open(os.path.join(abspath, "__dir__.md")) as infile:
                    self.text = infile.read()
            except OSError:
                self.text = ""
            for name in sorted(os.listdir(abspath)):
                if name.startswith("_"): continue
                if name.endswith("~"): continue
                note = Note(self.path, os.path.splitext(name)[0])
                self.subnotes.append(note)
                note.read()
        else:
            # It's a file; no subnotes.
            with open(f"{abspath}.md") as infile:
                self.text = infile.read()

    def build(self):
        "Build the lookup."
        LOOKUP[self.path] = self
        for note in self.subnotes:
            note.build()

    def get_tree(self):
        "Get the note contents as a dict."
        return {"parent": self.parent,
                "title": self.title,
                "path": self.path,
                "text": self.text,
                "subnotes": [s.get_tree() for s in self.subnotes]}


class HtmlRenderer(marko.html_renderer.HTMLRenderer):
    """Extension of HTML renderer to allow setting <a> attribute '_target'
    to '_blank', when the title begins with an exclamation point '!'.
    """

    def render_link(self, element):
        if element.title and element.title.startswith('!'):
            template = '<a target="_blank" href="{}"{}>{}</a>'
            element.title = element.title[1:]
        else:
            template = '<a href="{}"{}>{}</a>'
        title = (
            ' title="{}"'.format(self.escape_html(element.title))
            if element.title
            else ""
        )
        url = self.escape_url(element.dest)
        body = self.render_children(element)
        return template.format(url, title, body)

def markdown(value):
    "Process the value using Marko markdown."
    processor = marko.Markdown(renderer=HtmlRenderer)
    return jinja2.utils.Markup(processor.convert(value or ""))

def redirect_error(message, url=None):
    """"Return redirect response to the given URL, or referrer, or home page.
    Flash the given message.
    """
    flash_error(message)
    return flask.redirect(url or 
                          flask.request.headers.get("referer") or 
                          flask.url_for("home"))

def flash_error(msg): flask.flash(str(msg), "error")

def flash_warning(msg): flask.flash(str(msg), "warning")

def flash_message(msg): flask.flash(str(msg), "message")


app = flask.Flask(__name__)

app.add_template_filter(markdown)

DB = dict()

@app.before_first_request
def setup():
    "Read all notes and keep in memory. Set up links and indexes."
    global NOTE
    NOTE = Note(None, None)
    NOTE.read()
    NOTE.build()
    print(json.dumps(NOTE.get_tree(), indent=2))

@app.context_processor
def setup_template_context():
    "Add to the global context of Jinja2 templates."
    return dict(interactive=True,
                flash_error=flash_error,
                flash_warning=flash_warning,
                flash_message=flash_message,
                redirect_error=redirect_error)

@app.route("/")
def home():
    "Home page; root note."
    return flask.render_template("home.html", root=NOTE)

@app.route("/create", methods=["GET", "POST"])
def create():
    "Create a new note."
    if flask.request.method == "GET":
        parent = flask.request.values.get("parent") or ''
        return flask.render_template("create.html", parent=parent)

    elif flask.request.method == "POST":
        title = flask.request.form.get("title") or "No title"
        # Clean up title.
        title = title.replace("\n", " ")
        title = title.replace("/", " ")
        title = title.strip()
        title = title.lstrip(".")
        title = title.lstrip("_")
        # Clean up parent path.
        parent = flask.request.form.get("parent") or ""
        parent = parent.replace("\n", " ")
        parent = parent.strip()
        parent = parent.strip("/")
        text = flask.request.form.get("text") or ""
        return flask.redirect(flask.url_for('note', path=path))

@app.route("/note")
@app.route("/note/")
def root():
    "Root note information is shown in the home page."
    return flask.redirect(flask.url_for("home"))

@app.route("/note/<path:path>")
def note(path):
    "Display page for the given note."
    try:
        note = LOOKUP[path]
    except KeyError:
        return redirect_error(
            "No such note.",
            url=flask.url_for('note', path=os.path.dirname(path)))
    return flask.render_template("note.html", 
                                 note=note,
                                 segments=path.split("/"))

@app.route("/edit/<path:path>", methods=["GET", "POST"])
def edit(path):
    "Edit the given note."
    try:
        note = NOTE.get(path)
    except KeyError:
        return redirect_error(
            "No such note.",
            url=flask.url_for('note', path=os.path.dirname(path)))
    if flask.request.method == "GET":
        return flask.render_template("edit.html", note=note)

    elif flask.request.method == "POST":
        dirpath = os.path.join(SETTINGS["NOTES_ROOT"], path)
        if os.path.isdir(dirpath):
            title = "__dir__"
        else:
            dirpath, title = os.path.split(dirpath)
        write_note(dirpath, title, flask.request.form.get("text") or '')
        return flask.redirect(flask.url_for("note", path=path))

@app.route("/delete/<path:path>", methods=["POST"])
def delete(path):
    "Delete the given note."
    try:
        raise NotImplementedError
    except KeyError as error:
        flash_error(error)
    return flask.redirect(flask.url_for("note", path=os.path.dirname(path)))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        dirpath = os.path.expanduser(sys.argv[1])
        dirpath = os.path.normpath(dirpath)
    else:
        dirpath = os.path.join(os.getcwd(), "notes")
    if not os.path.exists(dirpath):
        sys.exit(f"no such directory '{dirpath}'")
    if not os.path.isdir(dirpath):
        sys.exit(f"'{dirpath}' is not a directory")
    try:
        filepath = os.path.join(dirpath, ".settings.json")
        with open(filepath) as infile:
            SETTINGS.update(json.load(infile))
        SETTINGS["SETTINGS_FILEPATH"] = filepath
    except OSError:
        SETTINGS["SETTINGS_FILEPATH"] = None
    SETTINGS["NOTES_ROOT"] = dirpath
    app.config.from_mapping(SETTINGS)
    app.run(debug=True)
