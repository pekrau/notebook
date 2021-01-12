"Simple app for personal notes. Optionally publish using GitHub pages."

__version__ = "0.0.4"

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

def read_index(dirpath):
    with open(os.path.join(dirpath, ".folder.json")) as infile:
        index = json.load(infile)
    return index

def write_index(dirpath, index):
    with open(os.path.join(dirpath, ".folder.json"), "w") as outfile:
        json.dump(index, outfile)

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
    "Create or repair folder index files."
    for dirpath, dirnames, filenames in os.walk(settings["NOTES_ROOT"]):
        indexfilepath = os.path.join(dirpath, ".folder.json")
        try:
            index = read_index(dirpath)
            orig_index = copy_module.deepcopy(index)
        except OSError:
            index = dict(folders=[], notes=[])
            orig_index = dict() # This will force file update further down.
        added = set(dirnames).difference(index["folders"])
        if added:
            index["folders"].extend(sorted(added))
        removed = set(index["folders"]).difference(dirnames)
        for remove in removed:
            index["folders"].remove(remove)
        filenames = [fn for fn in filenames if not fn.startswith(".")]
        notetitles = [os.path.splitext(fn)[0] for fn in filenames]
        added = set(notetitles).difference(index["notes"])
        if added:
            index["notes"].extend(sorted(added))
        removed = set(index["notes"]).difference(notetitles)
        for remove in removed:
            index["notes"].remove(remove)
        if index != orig_index:
            write_index(dirpath, index)

@app.context_processor
def setup_template_context():
    "Add to the global context of Jinja2 templates."
    return dict(enumerate=enumerate,
                flash_error=flash_error,
                flash_warning=flash_warning,
                flash_message=flash_message,
                redirect_error=redirect_error,
                join_path=join_path)

@app.route("/")
def home():
    "Home page; dashboard."
    root = settings["NOTES_ROOT"]
    index = read_index(root)
    return flask.render_template("home.html",
                                 folders=index["folders"],
                                 notes=index["notes"])

@app.route("/notes")
def root():
    "Root of notes; redirect to home."
    return flask.redirect(flask.url_for("home"))

@app.route("/create", methods=["GET", "POST"])
def create():
    "Create a note."
    if flask.request.method == "GET":
        return flask.render_template("create.html",
                                     folder=flask.request.form.get("folder"))
    elif flask.request.method == "POST":
        title = flask.request.form.get("title") or "No title"
        title = title.replace("\n", " ")
        title = title.replace("/", " ")
        title = title.strip()
        title = title.lstrip(".")
        folder = flask.request.form.get("folder") or ""
        folder = folder.replace("\n", " ")
        folder = folder.strip()
        folder = folder.strip("/")
        text = flask.request.form.get("text") or ""
        dirpath = os.path.join(settings["NOTES_ROOT"], folder)
        if not os.path.exists(dirpath):
            try:
                os.makedirs(dirpath)
            except OSError as error:
                return redirect_error(error)
        filepath = os.path.join(dirpath, f"{title}.md")
        count = 1
        while os.path.exists(filepath):
            count += 1
            filepath = os.path.join(dirpath, f"{title}-{count}.md")
        try:
            with open(filepath, "w") as outfile:
                outfile.write(text)
        except IOError as error:
            return redirect_error(error)
        return flask.redirect(flask.url_for('note', title=title))

@app.route("/notes/<path:path>")
def item(path):
    "Display page for note or folder."
    # Is it a directory = folder?
    dirpath = os.path.join(settings["NOTES_ROOT"], path)
    if os.path.isdir(dirpath):
        index = read_index(dirpath)
        if path:
            path = path.split("/")
        else:
            path = []
        return flask.render_template("folder.html",
                                     path=path,
                                     folders=index["folders"],
                                     notes=index["notes"])
    # Is it a Markdown file = note?
    filepath = os.path.join(settings["NOTES_ROOT"], f"{path}.md")
    if os.path.isfile(filepath):
        try:
            with open(filepath) as infile:
                text = infile.read()
        except OSError as error:
            return redirect_error(error)
        path, title = os.path.split(path) # Yes, the original path.
        if path:
            path = path.split("/")
        else:
            path = []
        return flask.render_template("note.html",
                                     path=path,
                                     title=title,
                                     text=text)

    return redirect_error("No such folder or note.")

@app.route("/edit/<path:path>", methods=["POST"])
def edit(path):
    "Edit the text of a note."
    if flask.request.method == "GET":
        return flask.render_template("create.html",
                                     folder=flask.request.form.get("folder"))
    if flask.request.method == "POST":
        title = flask.request.form.get("title") or "No title"
        title = title.replace("\n", " ")
        title = title.replace("/", " ")
        title = title.strip()
        title = title.lstrip(".")
        folder = flask.request.form.get("folder") or ""
        folder = folder.replace("\n", " ")
        folder = folder.strip()
        folder = folder.strip("/")
        text = flask.request.form.get("text") or ""
        dirpath = os.path.join(settings["NOTES_ROOT"], folder)
        if not os.path.exists(dirpath):
            try:
                os.makedirs(dirpath)
            except OSError as error:
                return redirect_error(error)
        filepath = os.path.join(dirpath, f"{title}.md")
        count = 1
        while os.path.exists(filepath):
            count += 1
            filepath = os.path.join(dirpath, f"{title}-{count}.md")
        try:
            with open(filepath, "w") as outfile:
                outfile.write(text)
        except IOError as error:
            return redirect_error(error)
        return flask.redirect(flask.url_for('note', title=title))


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
        filepath = os.path.join(dirpath, "settings.json")
        with open(filepath) as infile:
            settings.update(json.load(infile))
        settings["SETTINGS_FILEPATH"] = filepath
    except IOError:
        settings["SETTINGS_FILEPATH"] = None
    settings["NOTES_ROOT"] = dirpath
    app.config.from_mapping(settings)
    app.run(debug=True)
