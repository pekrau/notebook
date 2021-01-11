"Simple app for personal notes. Optionally publish using GitHub pages."

__version__ = "0.0.1"

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
    return flask.redirect(url or referrer_or_home())

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
    return flask.render_template("home.html")


if __name__ == "__main__":
    import sys
    import os
    if len(sys.argv) > 1:
        dirpath = sys.argv[1]
        dirpath = os.path.expanduser(dirpath)
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
        pass
    settings["NOTESPATH"] = dirpath
    app.config.from_mapping(settings)
    app.run()
