"Simple app for personal notes. Optionally publish using GitHub pages."

__version__ = "0.0.6"

import copy as copy_module
import json
import os

import flask
import marko
import jinja2.utils


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
                          flask.request.headers.get('referer') or 
                          flask.url_for('home'))

def flash_error(msg):
    "Flash error message."
    flask.flash(str(msg), "error")

def flash_warning(msg):
    "Flash warning message."
    flask.flash(str(msg), "warning")

def flash_message(msg):
    "Flash information message."
    flask.flash(str(msg), "message")

def join_path(*args):
    "Join together arguments (strings or lists of strings) into a path."
    parts = []
    for arg in args:
        if isinstance(arg, list):
            parts.extend(arg)
        else:
            parts.append(str(arg))
    return "/".join(parts)

def get_index(path):
    """Return the index file for the directory.
    If it doesn't exist, create it.
    """
    try:
        with open(os.path.join(path, ".index.json")) as infile:
            return json.load(infile)
    except OSError:
        filenames = os.listdir(path)
        filenames = [fn for fn in filenames 
                     if not (fn.startswith(".") or fn.startswith("_"))]
        filenames = [os.path.splitext(fn)[0] for fn in filenames]
        index = dict(notes=sorted(filenames))
        write_index(path, index)
        return index

def write_index(path, index):
    "Write the index information to a file in the directory."
    with open(os.path.join(path, ".index.json"), "w") as outfile:
        json.dump(index, outfile)

def get_note(path, level=1):
    """Get the note at the given path.
    If any subnotes, provide these as a list of dictionaries.
    Recursively go down the given number of levels.
    """
    if path:
        dirpath = os.path.join(settings["NOTES_ROOT"], path)
    else:
        dirpath = settings["NOTES_ROOT"]
    result = {"title": path and os.path.basename(path) or None}

    # Is it a directory? Note containing other notes.
    if os.path.isdir(dirpath):
        try:
            with open(os.path.join(dirpath, "_dir.md")) as infile:
                result["text"] = infile.read()
        except OSError:
            result["text"] = ""
        result["notes"] = []
        if level >= 0:
            with open(os.path.join(dirpath, ".index.json")) as infile:
                index = json.load(infile)
            for title in index["notes"]:
                if path:
                    path2 = os.path.join(path, title)
                else:
                    path2 = title
                result["notes"].append(get_note(path2, level-1))

    # Is it a Markdown file? A single note.
    else:
        filepath = os.path.join(settings["NOTES_ROOT"], f"{path}.md")
        with open(filepath) as infile:
            result["text"] = infile.read()

    return result


app = flask.Flask(__name__)

settings = dict(VERSION=__version__,
                SERVER_NAME="127.0.0.1:5099",
                SECRET_KEY="this is a secret",
                TEMPLATES_AUTO_RELOAD=True,
                DEBUG=True,
                JSON_AS_ASCII=False)

app.add_template_filter(markdown)

@app.before_first_request
def setup():
    "Check index files recursively; create or repair."
    pass
    for dirpath, dirnames, filenames in os.walk(settings["NOTES_ROOT"]):
        try:
            with open(dirpath) as infile:
                index = json.load(infile)
            orig_index = copy_module.deepcopy(index)
        except OSError:
            index = dict(notes=[])
            orig_index = dict() # This will force file update further down.
        filenames = [fn for fn in filenames 
                     if not (fn.startswith(".") or fn.startswith("_"))]
        filenames = [os.path.splitext(fn)[0] for fn in filenames]
        current = set(dirnames).union(filenames)
        added = current.difference(index["notes"])
        if added:
            print("added", added)
            index["notes"].extend(sorted(added))
        removed = set(index["notes"]).difference(current)
        if removed:
            print("removed", removed)
        for remove in removed:
            index["notes"].remove(remove)
        if index != orig_index:
            write_index(dirpath, index)

@app.context_processor
def setup_template_context():
    "Add to the global context of Jinja2 templates."
    return dict(enumerate=enumerate,
                len=len,
                flash_error=flash_error,
                flash_warning=flash_warning,
                flash_message=flash_message,
                redirect_error=redirect_error,
                join_path=join_path)

@app.route("/")
def home():
    "Home page; root note."
    return flask.render_template("home.html", root=get_note(None, level=1))

@app.route("/new", methods=["GET", "POST"])
def new():
    "Create a new note."
    if flask.request.method == "GET":
        return flask.render_template("new.html",
                                     parent=flask.request.values.get("parent"))

    elif flask.request.method == "POST":
        title = flask.request.form.get("title") or "No title"
        title = title.replace("\n", " ")
        title = title.replace("/", " ")
        title = title.strip()
        title = title.lstrip(".")
        parent = flask.request.form.get("parent") or ""
        parent = parent.replace("\n", " ")
        parent = parent.strip()
        parent = parent.strip("/")
        text = flask.request.form.get("text") or ""
        dirpath = os.path.join(settings["NOTES_ROOT"], parent)
        if not os.path.exists(dirpath):
            try:
                os.makedirs(dirpath)
            except OSError as error:
                return redirect_error(error)
        index = get_index(dirpath)
        orig_title = title
        filepath = os.path.join(dirpath, f"{title}.md")
        count = 1
        while os.path.exists(filepath):
            count += 1
            title = f"{orig_title}-{count}"
            filepath = os.path.join(dirpath, f"{title}.md")
        try:
            with open(filepath, "w") as outfile:
                outfile.write(text)
        except IOError as error:
            return redirect_error(error)
        index["notes"].append(title)
        write_index(dirpath, index)
        if parent:
            path = os.path.join(parent, title)
        else:
            path = title
        return flask.redirect(flask.url_for('note', path=path))

@app.route("/note")
def root():
    "Root note information is shown in the home page."
    return flask.redirect(flask.url_for("home"))

@app.route("/note/<path:path>")
def note(path):
    "Display page for a note."
    note = get_note(path, level=1)
    return flask.render_template("note.html", 
                                 note=note,
                                 segments=path.split("/"))

@app.route("/edit/<path:path>", methods=["POST"])
def edit(path):
    "Edit the text of a note."
    raise NotImplementedError


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
        filepath = os.path.join(dirpath, ".notes.json")
        with open(filepath) as infile:
            settings.update(json.load(infile))
        settings["SETTINGS_FILEPATH"] = filepath
    except IOError:
        settings["SETTINGS_FILEPATH"] = None
    settings["NOTES_ROOT"] = dirpath
    app.config.from_mapping(settings)
    app.run(debug=True)
