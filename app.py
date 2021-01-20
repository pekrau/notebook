"Simple app for personal notes. Optionally publish using GitHub pages."

__version__ = "0.2.3"

import json
import os

import flask
import marko
import jinja2.utils


SETTINGS = dict(VERSION=__version__,
                SERVER_NAME="127.0.0.1:5099",
                SECRET_KEY="this is a secret key",
                TEMPLATES_AUTO_RELOAD=True,
                DEBUG=True,
                JSON_AS_ASCII=False,
                NOTES_DIRPATH="notes")


class Note:
    "Note and its subnotes, if any."

    def __init__(self, supernote, title, text=""):
        self.supernote = supernote
        if supernote:
            supernote.subnotes.append(self)
        self.subnotes = []
        self._title = title
        self._text = text

    def __repr__(self):
        return self.path

    def get_title(self):
        return self._title

    def set_title(self, title):
        """Set a new title.
        Raise ValueError if the title is invalid; bad start or end characters.
        Raise KeyError if there is already a note with that title
        """
        # XXX update lookup for this and all subnotes
        # XXX update links
        if not self.supernote: return  # Root note has no title to change.
        title = title.strip()
        if not title: raise ValueError
        if "/" in title: raise ValueError
        if title[0] == ".": raise ValueError
        if title[0] == "_": raise ValueError
        if title[-1] == "~": raise ValueError
        if self._title == title: return
        new_abspath = os.path.join(SETTINGS["NOTES_DIRPATH"],
                                   self.supernote.path,
                                   title)
        if os.path.exists(new_abspath): raise KeyError
        if os.path.exists(f"{new_abspath}.md"): raise KeyError
        # Remove this note and below from lookup while old path.
        for note in self.traverse():
            note.remove()
        # Old abspath needed for renaming directory/file.
        old_abspath = self.abspath
        # Actually change the title of the note.
        self._title = title
        if os.path.isdir(old_abspath):
            os.rename(old_abspath, self.abspath)  # New abspath
        else:
            os.rename(f"{old_abspath}.md", f"{self.abspath}.md")
        # Add this note and below to lookup with new path.
        for note in self.traverse():
            note.add()

    title = property(get_title, set_title, doc="The title of the note.")

    def get_text(self):
        return self._text

    def set_text(self, text):
        # XXX update links etc
        self._text = text
        abspath = self.abspath
        if os.path.isdir(abspath):
            with open(os.path.join(abspath, "__dir__.md"), "w") as outfile:
                outfile.write(text)
        else:
            with open(f"{abspath}.md", "w") as outfile:
                outfile.write(text)

    text = property(get_text, set_text,
                    doc="The Markdown-formatted text of the note.")

    @property
    def path(self):
        "Return the path of the note."
        if self.supernote:
            assert self.title
            return os.path.join(self.supernote.path, self.title)
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
            return  os.path.join(SETTINGS["NOTES_DIRPATH"], path)
        else:
            return SETTINGS["NOTES_DIRPATH"]

    @property
    def url(self):
        if self.path:
            return flask.url_for("note", path=self.path)
        else:
            return flask.url_for("home")

    @property
    def count(self):
        "Return the number of subnotes."
        return len(self.subnotes)

    def count_traverse(self):
        "Return the number of subnotes recursively, including this one."
        result = 1
        for subnote in self.subnotes:
            result += subnote.count_traverse()
        return result

    def supernotes(self):
        "Return the list of supernotes."
        if self.supernote:
            return self.supernote.supernotes() + [self.supernote]
        else:
            return []

    def traverse(self):
        yield self
        for subnote in self.subnotes:
            yield from subnote.traverse()

    def write(self):
        "Write this note to disk. Does NOT write subnotes."
        if os.path.isdir(self.abspath):
            with open(os.path.join(self.abspath, "__dir__.md"), "w") as outfile:
                outfile.write(self.text)
        else:
            with open(f"{self.abspath}.md", "w") as outfile:
                outfile.write(self.text)

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
            for filename in sorted(os.listdir(abspath)):
                if filename.startswith("."): continue
                if filename.startswith("_"): continue
                if filename.endswith("~"): continue
                note = Note(self, os.path.splitext(filename)[0])
                note.read()
        else:
            # It's a file; no subnotes.
            with open(f"{abspath}.md") as infile:
                self.text = infile.read()

    def add(self):
        "Add the note to the lookup."
        LOOKUP[self.path] = self

    def remove(self, path=None):
        "Remove the note from the lookup."
        LOOKUP.pop(path or self.path)

    def create_subnote(self, title, text):
        "Create and return a subnote."
        if title in self.subnotes:
            raise ValueError(f"Note already exists: '{title}'")
        if os.path.isfile(f"{self.abspath}.md"):
            abspath = self.abspath
            os.mkdir(abspath)
            os.rename(f"{abspath}.md", os.path.join(abspath, "__dir__.md"))
        note = Note(self, title, text)
        self.subnotes.sort(key=lambda n: n.title)
        note.write()
        note.add()
        return note

    def is_deletable(self):
        """May this note be deleted?
        - Must have no subnotes.
        - XXX Must have no links to it.
        """
        if self.supernote is None: return False
        if self.count: return False
        return True

    def delete(self):
        "Delete this note."
        if not self.is_deletable():
            raise ValueError("This note may not be deleted.")
        # XXX remove links
        os.remove(f"{self.abspath}.md")
        self.supernote.subnotes.remove(self)
        # Convert supernote to file if no subnotes any longer.
        if self.supernote.count == 0:
            abspath = self.supernote.abspath
            os.rename(os.path.join(abspath, "__dir__.md"), f"{abspath}.md")
            os.rmdir(abspath)

    def get_tree(self):
        "Get the note contents as a dict."
        result = {"title": self.title,
                  "path": self.path,
                  "text": self.text,
                  "subnotes": [s.get_tree() for s in self.subnotes]}
        if self.supernote:
            result["supernote"] = self.supernote.path
        return result


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

def flash_error(msg): flask.flash(str(msg), "error")

def flash_warning(msg): flask.flash(str(msg), "warning")

def flash_message(msg): flask.flash(str(msg), "message")


ROOT = Note(None, None)
LOOKUP = dict()

app = flask.Flask(__name__)

app.add_template_filter(markdown)

@app.before_first_request
def setup():
    "Read all notes and keep in memory. Set up lookup."
    # XXX links
    ROOT.read()
    for note in ROOT.traverse():
        note.add()
    print(json.dumps(ROOT.get_tree(), indent=2))
    print(list(ROOT.traverse()))

@app.context_processor
def setup_template_context():
    "Add to the global context of Jinja2 templates."
    return dict(interactive=True,
                flash_error=flash_error,
                flash_warning=flash_warning,
                flash_message=flash_message)

@app.route("/")
def home():
    "Home page; root note."
    return flask.render_template("home.html", root=ROOT)

@app.route("/note")
@app.route("/note/")
def root():
    "Root note is shown in the home page."
    return flask.redirect(flask.url_for("home"))

@app.route("/create", methods=["GET", "POST"])
def create():
    "Create a new note."
    if flask.request.method == "GET":
        try:
            supernote = LOOKUP[flask.request.values["supernote"]]
        except KeyError:
            supernote = None    # Root supernote.
        try:
            source = LOOKUP[flask.request.values["source"]]
        except KeyError:
            source = None
        return flask.render_template("create.html",
                                     supernote=supernote,
                                     source=source)

    elif flask.request.method == "POST":
        try:
            superpath = flask.request.form["supernote"]
            if not superpath: raise KeyError
        except KeyError:
            supernote = ROOT
        else:
            try:
                supernote = LOOKUP[superpath]
            except KeyError:
                raise
                flash_error(f"No such supernote: '{superpath}'")
                return flask.redirect(flask.url_for("home"))
        title = flask.request.form.get("title") or "No title"
        title = title.replace("\n", " ")  # Clean up title.
        title = title.replace("/", " ")
        title = title.strip()
        title = title.lstrip(".")
        title = title.lstrip("_")
        text = flask.request.form.get("text") or ""
        try:
            note = supernote.create_subnote(title=title, text=text)
        except ValueError as error:
            flash_error(error)
            return flask.redirect(supernote.url)
        return flask.redirect(note.url)

@app.route("/note/<path:path>")
def note(path):
    "Display page for the given note."
    try:
        note = LOOKUP[path]
    except KeyError:
        flash_error(f"No such note: '{path}'")
        return flask.redirect(flask.url_for("note", path=os.path.dirname(path)))
    return flask.render_template("note.html", note=note)

@app.route("/edit/", methods=["GET", "POST"])
@app.route("/edit/<path:path>", methods=["GET", "POST"])
def edit(path=""):
    "Edit the given note; title (i.e. file/directory rename) and/or text."
    try:
        note = LOOKUP[path]
    except KeyError:
        flash_error(f"No such note: '{path}'")
        return flask.redirect(flask.url_for("note", path=os.path.dirname(path)))

    if flask.request.method == "GET":
        return flask.render_template("edit.html", note=note)

    elif flask.request.method == "POST":
        try:
            title = flask.request.form.get("title") or ""
            note.title = title
        except ValueError:
            flash_error(f"Invalid title: '{title}'")
            return flask.redirect(flask.url_for("edit", path=path))
        except KeyError:
            flash_error(f"Note already exists: '{title}'")
            return flask.redirect(flask.url_for("edit", path=path))
        note.text = flask.request.form.get("text") or ''
        return flask.redirect(note.url)

@app.route("/delete/<path:path>", methods=["POST"])
def delete(path):
    "Delete the given note."
    try:
        note = LOOKUP[path]
    except KeyError:
        flash_error(f"No such note: '{path}'")
        return flask.redirect(flask.url_for("note", path=os.path.dirname(path)))
    try:
        note.delete()
    except ValueError as error:
        flash_error(error)
        return flask.redirect(note.url)
    return flask.redirect(note.supernote.url)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        dirpath = os.path.expanduser(sys.argv[1])
        dirpath = os.path.normpath(dirpath)
    else:
        dirpath = os.path.join(os.getcwd(), "notes")
    if not os.path.exists(dirpath):
        sys.exit(f"No such directory: {dirpath}")
    if not os.path.isdir(dirpath):
        sys.exit(f"Not a directory: {dirpath}")
    try:
        filepath = os.path.join(dirpath, ".settings.json")
        with open(filepath) as infile:
            SETTINGS.update(json.load(infile))
        SETTINGS["SETTINGS_FILEPATH"] = filepath
    except OSError:
        SETTINGS["SETTINGS_FILEPATH"] = None
    SETTINGS["NOTES_DIRPATH"] = dirpath
    app.config.from_mapping(SETTINGS)
    app.run(debug=True)
