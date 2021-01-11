"Simple app for personal notes. Optionally publish using GitHub pages."

__version__ = "0.0.3"

import flask
import marko

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
    flask.flash(str(msg), 'error')

def flash_warning(msg):
    "Flash warning message."
    flask.flash(str(msg), 'warning')

def flash_message(msg):
    "Flash information message."
    flask.flash(str(msg), 'message')


app = flask.Flask(__name__)

settings = dict(VERSION=__version__,
                SERVER_NAME="127.0.0.1:5099",
                TEMPLATES_AUTO_RELOAD=True,
                DEBUG=True,
                JSON_AS_ASCII=False)

app.add_template_filter(markdown)

@app.context_processor
def setup_template_context():
    "Add to the global context of Jinja2 templates."
    return dict(flash_error=flash_error,
                flash_warning=flash_warning,
                flash_message=flash_message,
                redirect_error=redirect_error)

@app.route('/')
def home():
    "Home page; dashboard."
    root = settings["NOTES_ROOT"]
    items = sorted(os.listdir(root))
    folders = [i for i in items if os.path.isdir(os.path.join(root, i))]
    notes = [os.path.splitext(i)[0] for i in items 
             if os.path.isfile(os.path.join(root, i))]
    return flask.render_template("home.html", folders=folders, notes=notes)

@app.route('/notes/<path:path>')
def folder(path):
    "Folder page."
    raise NotImplementedError
    root = settings["NOTES_ROOT"]
    items = sorted(os.listdir(root))
    folders = [i for i in items if os.path.isdir(os.path.join(root, i))]
    notes = [os.path.splitext(i)[0] for i in items 
             if os.path.isfile(os.path.join(root, i))]
    return flask.render_template("home.html", folders=folders, notes=notes)

@app.route('/notes/<path:path>')
def note(path):
    "Note page."
    raise NotImplementedError

@app.route('/create', methods=["GET", "POST"])
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
                redirect_error(error)
        filepath = os.path.join(dirpath, f"{title}.md")
        count = 1
        while os.path.exists(filepath):
            count += 1
            filepath = os.path.join(dirpath, f"{title}{count}.md")
        try:
            with open(filepath, "w") as outfile:
                outfile.write(f"# {title}\n\n{text}")
        except IOError as error:
            redirect_error(error)
        return flask.redirect(flask.url_for('note', title=title))


if __name__ == "__main__":
    import sys
    import os
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
