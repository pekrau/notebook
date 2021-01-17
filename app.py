"Simple app for personal notes. Optionally publish using GitHub pages."

__version__ = "0.1.2"

import base64
import copy as copy_module
import json
import os
import shutil
import urllib.parse

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
                          flask.request.headers.get("referer") or 
                          flask.url_for("home"))

def flash_error(msg): flask.flash(str(msg), "error")

def flash_warning(msg): flask.flash(str(msg), "warning")

def flash_message(msg): flask.flash(str(msg), "message")

def join_path(*args, idify=False):
    """Join together arguments (strings or lists of strings) into a path.
    Optionally convert it into a valid id for HTML code.
    """
    parts = []
    for arg in args:
        if isinstance(arg, list):
            parts.extend(arg)
        else:
            parts.append(str(arg))
    path = "/".join(parts)
    if idify:
        path = path.replace("/", "-").replace(" ", "_").replace(",", "_")
    return path

def write_note(dirpath, title, text):
    "Write the note text to a file named by the dirpath and title."
    with open(os.path.join(dirpath, f"{title}.md"), "w") as outfile:
        outfile.write(text)
    # XXX update links in database

def retitle_note(dirpath, current, new):
    "Change the title of the note."
    # XXX update links in database
    # XXX update links in other texts
    
def delete_note(path):
    "Delete the note, recursively."
    assert path, "cannot delete root"
    print("delete", path)
    dirpath = os.path.join(settings["NOTES_ROOT"], path)
    # XXX update links in database
    if os.path.isdir(dirpath):
        print("rmtree", dirpath)
        shutil.rmtree(dirpath)
    else:
        print("remove", f"{dirpath}.md")
        os.remove(f"{dirpath}.md")
    # Fix the index of the parent.
    dirpath, title = os.path.split(dirpath)
    index = get_index(dirpath)
    # If the parent has no other children, convert it into a file.
    if len(index["notes"]) == 1:
        os.rename(os.path.join(dirpath, "__dir__.md"), f"{dirpath}.md")
        os.remove(os.path.join(dirpath, ".index.json"))
        os.rmdir(dirpath)
    else:
        index["notes"].remove(os.path.basename(path))
        write_index(dirpath, index)

def get_index(dirpath):
    "Return the index file for the directory."
    with open(os.path.join(dirpath, ".index.json")) as infile:
        return json.load(infile)

def write_index(dirpath, index):
    "Write the index information to a file in the directory."
    with open(os.path.join(dirpath, ".index.json"), "w") as outfile:
        json.dump(index, outfile)

def make_index(dirpath):
    "Create an index file for the directory if it does not exist."
    if os.path.exists(os.path.join(dirpath, ".index.json")):
        return False
    else:
        notes = []
        for name in os.listdir(dirpath):
            if os.path.isdir(os.path.join(dirpath, name)):
                notes.append(name)
            elif not (name.startswith(".") or name.startswith("_")):
                notes.append(os.path.splitext(name)[0])
        write_index(dirpath, {"notes": notes})
        return True

def get_note(path, level=1):
    """Get the note at the given path.
    If any subnotes, provide these as a list of dictionaries.
    Recursively go down the given number of levels.
    """
    if path:
        path = urllib.parse.unquote(path)
        dirpath = os.path.join(settings["NOTES_ROOT"], path)
    else:
        dirpath = settings["NOTES_ROOT"]
    result = {"path": path,
              "title": path and os.path.basename(path) or None}

    # Is it a directory? Note containing other notes.
    if os.path.isdir(dirpath):
        try:
            with open(os.path.join(dirpath, "__dir__.md")) as infile:
                result["text"] = infile.read()
        except OSError:
            result["text"] = ""
        result["notes"] = []
        if level >= 0:
            index = get_index(dirpath)
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
            index = get_index(dirpath)
            orig_index = copy_module.deepcopy(index)
        except OSError:
            index = dict(notes=[])
            orig_index = dict() # This will force file update further down.
        filenames = [fn for fn in filenames if not (fn.startswith(".") or
                                                    fn.startswith("_") or
                                                    fn.endswith("~"))]
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
    return dict(interactive=True,
                enumerate=enumerate,
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

@app.route('/icon')
def icon():
    "Return the PNG icon for the app."
    return flask.make_response((ICON, {"Content-Type": "image/png"}))

# Base64-encoded PNG 32x32 image.
ICON = base64.b64decode(b"iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAACXBIWXMAACBAAAAgQAHitCyxAAAAGXRFWHRTb2Z0d2FyZQB3d3cuaW5rc2NhcGUub3Jnm+48GgAAAgJJREFUWIW917trFEEcwPFPvOQkOUURLbTyhaCIESxsQxSxESxSqJ2FNlpY+wdYpxFRrNQu4PuBbzEi2AlKjKJgVJBosLAQRC+x2FlyiXt7u3t7+cEwO8/vd2Zv53ZZuFiOUbzDhriyK+T7cAJrC05exzHcb9K+DHexM5S/YAAfYAgzJaSTKYI3EvpPYF0XXqIf13Ep+6LnxC/cw58m7dvwECvn1Y8Jg2awoyC8WSzFMGqh3I8pc3fhhYZCf4nwGh6HeUexJEFiHKs7IdDXAI/T0waJ7XiONfGAMgVqeCL5R/oAvUmDyhLow6Mm8Did65RAr2iFafCPmpwz7Qosxs2i8HYFqpIPmf8OnLRJigqUAi8qUMW1FvBPWJ9lsrwCVVxtAf+s4R9vXmzFeWwpItCDKxngG1PmOB36DcOiDNA4KriA/Sl9JrEH71P6dIe8J49ABRdxoAV8EG8yzimrQLzygyl9vgX4WB54VoFTOJTSPil6u8kNzyLQjcMp7d+xW85tzyMwiFUp8F14XRSeRWCoSf1UgL9qB95KoCL5kZsQbXvbcGafyaQYMLv9P3ALI7iDv2XAWwn8xhlcFr1i1cuCZhV4FlJHI89R3DGB6YbrhYhKyKeJbsFbbMZxnNWhex1iBfaG6/G48ohyvg3zpK9BBtEX8lHRWV7vMPgnbmNTDP8HkTP9qMo5nowAAAAASUVORK5CYII=")

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
        dirpath = os.path.join(settings["NOTES_ROOT"], parent)
        # Check that the note does not already exist.
        if os.path.exists(os.path.join(dirpath, title)) or \
           os.path.exists(os.path.join(dirpath, f"{title}.md")):
            return redirect_error("A note with this title already exists.")
        # Create directory(ies) that do not exist.
        if not os.path.exists(dirpath):
            try:
                os.makedirs(dirpath)
            except OSError as error:
                return redirect_error(error)
            else:
                # Move any note file down into its created directory.
                dirpath2 = dirpath
                while dirpath2 != settings["NOTES_ROOT"]:
                    filepath = f"{dirpath2}.md"
                    if os.path.isfile(filepath):
                        os.rename(filepath, os.path.join(dirpath2,"__dir__.md"))
                        # Links are unaffected.
                        break
                    dirpath2 = os.path.dirname(dirpath2)
                dirpath2 = dirpath
                while make_index(dirpath2):
                    dirpath2 = os.path.dirname(dirpath2)
        index = get_index(dirpath)
        try:
            write_note(dirpath, title, text)
            index["notes"].append(title)
            write_index(dirpath, index)
        except OSError as error:
            return redirect_error(error)
        if parent:
            path = os.path.join(parent, title)
        else:
            path = title
        return flask.redirect(flask.url_for('note', path=path))

@app.route("/note")
@app.route("/note/")
def root():
    "Root note information is shown in the home page."
    return flask.redirect(flask.url_for("home"))

@app.route("/note/<path:path>")
def note(path):
    "Display page for a note."
    try:
        note = get_note(path, level=1)
    except OSError as error:
        return redirect_error(
            error, url=flask.url_for('note', path=os.path.dirname(path)))
    return flask.render_template("note.html", 
                                 note=note,
                                 segments=path.split("/"))

@app.route("/edit/<path:path>", methods=["GET", "POST"])
def edit(path):
    "Edit the note."
    try:
        note = get_note(path, level=0)
    except OSError as error:
        return redirect_error(
            error, url=flask.url_for('note', path=os.path.dirname(path)))
    if flask.request.method == "GET":
        return flask.render_template("edit.html", note=note)

    elif flask.request.method == "POST":
        dirpath = os.path.join(settings["NOTES_ROOT"], path)
        if os.path.isdir(dirpath):
            title = "__dir__"
        else:
            dirpath, title = os.path.split(dirpath)
        write_note(dirpath, title, flask.request.form.get("text") or '')
        return flask.redirect(flask.url_for("note", path=path))

@app.route("/delete/<path:path>", methods=["POST"])
def delete(path):
    "Delete the note, recursively."
    try:
        delete_note(path)
    except OSError as error:
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
        filepath = os.path.join(dirpath, ".notes.json")
        with open(filepath) as infile:
            settings.update(json.load(infile))
        settings["SETTINGS_FILEPATH"] = filepath
    except OSError:
        settings["SETTINGS_FILEPATH"] = None
    settings["NOTES_ROOT"] = dirpath
    app.config.from_mapping(settings)
    app.run(debug=True)
