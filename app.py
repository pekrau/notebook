"Simple app for personal scrapbooks stored in the file system."

__version__ = "1.0.9"

import collections
import importlib
import json
import os
import platform
import string
import time
import uuid

import flask
import marko
import marko.ast_renderer
import jinja2.utils


ROOT = None  # The root note. Created in 'setup'.
STARRED = set()  # Starred notes.
RECENT = None  # Deque of recently modified notes. Created in 'setup'.
BACKLINKS = dict()  # Map target note -> set of source notes.
HASHTAGS = dict()  # Map word -> set of notes.
ATTRIBUTES = dict()  # Map word -> map values -> set of notes.

OPERATIONS = dict()  # Map operation name -> operation object.


def get_settings_filepath():
    "Get the filepath for the user's settings file."
    return os.path.join(os.path.expanduser("~/.scrapbooks"))


def get_settings():
    "Return the settings."
    settings = dict(
        VERSION=__version__,
        SERVER_NAME="localhost.localdomain:5099",
        SECRET_KEY="this is a secret key",
        DEBUG=True,
        JSON_AS_ASCII=False,
        IMAGE_EXTENSIONS=[".png", ".jpg", ".jpeg", ".svg", ".gif"],
        TEXT_EXTENSIONS=[".pdf", ".docx", ".txt"],
        MAX_RECENT=12,
        SCRAPBOOKS=[],
    )
    filepath = get_settings_filepath()
    try:
        with open(filepath) as infile:
            settings.update(json.load(infile))
    except OSError:
        pass
    settings["SETTINGS_FILEPATH"] = filepath
    # Set the bad characters for titles/filenames.
    if platform.system() == "Linux":
        settings["BAD_CHARACTERS"] = "/\\.\n"
    else:  # Assume Windows; what about MacOS?
        settings["BAD_CHARACTERS"] = '<>:"/\\|?*/.\n'
    # The first scrapbook is the starting one.
    try:
        scrapbook = settings["SCRAPBOOKS"][0]
    except IndexError:  # No scrapbook at all.
        settings["SCRAPBOOK_DIRPATH"] = None
        settings["SCRAPBOOK_TITLE"] = None
    else:
        settings["SCRAPBOOK_DIRPATH"] = scrapbook
        settings["SCRAPBOOK_TITLE"] = os.path.basename(scrapbook)
    if settings["DEBUG"]:
        settings["TEMPLATES_AUTO_RELOAD"] = True
    return settings


def write_settings():
    """Write out the settings file with updated information.
    Update only the information that can be changed via the app.
    """
    filepath = get_settings_filepath()
    try:
        with open(filepath) as infile:
            settings = json.load(infile)
    except OSError:
        settings = {}
    with open(filepath, "w") as outfile:
        for key in ["SCRAPBOOKS"]:
            settings[key] = flask.current_app.config[key]
        json.dump(settings, outfile, indent=2)


def load_operations(app):
    "Load the operations modules specified in the settings."
    for name in app.config.get("OPERATIONS", []):
        module = importlib.import_module(name)
        OPERATIONS[name] = module.Operation(app.config)


def get_operations(note):
    "Get the list of operations relevant to the note."
    return [o for o in OPERATIONS.values() if o.is_relevant(note)]


class Note:
    "Note: title, text, and subnotes if any."

    def __init__(self, supernote, title):
        self.supernote = supernote
        if supernote:
            supernote.subnotes.append(self)
        self.subnotes = []
        if title is None:
            self._title = None
        else:
            self._title = cleanup_title(title)
        self._text = ""
        self._ast = None
        self.file_extension = None
        self.stale_links = []

    def __repr__(self):
        return self.path

    def __lt__(self, other):
        return self.title < other.title

    def __contains__(self, term):
        "Does this note contain the search term?"
        term = term.lower()
        if term in self.title.lower():
            return True
        if term in self.text.lower():
            return True
        return False

    @property
    def id(self):
        return f"i{id(self)}"

    def get_title(self):
        return self._title

    def set_title(self, title):
        """Set a new title, which changes its path.
        Updates notes that link to this note or its subnotes.
        Raise ValueError if the title is invalid; bad start or end characters.
        Raise KeyError if there is already a note with that title
        """
        if not self.supernote:
            return  # Root note has no title to change.
        title = cleanup_title(title)
        if not title:
            raise ValueError
        if title[0] == ".":
            raise ValueError
        if title[0] == "_":
            raise ValueError
        if title[-1] == "~":
            raise ValueError
        if self.title == title:
            return
        new_abspath = os.path.join(
            flask.current_app.config["SCRAPBOOK_DIRPATH"], self.supernote.path, title
        )
        if os.path.exists(new_abspath):
            raise KeyError
        if os.path.exists(new_abspath + ".md"):
            raise KeyError
        # The set of notes whose paths will change: this one and all below it.
        changing = list(self.traverse())
        # Remember the old path for each note whose paths will change.
        old_paths = [note.path for note in changing]
        # The set of notes which link to any of the changing-path notes.
        linking = set()
        for note in changing:
            linking.update(BACKLINKS.get(note, list()))
        # Old abspath needed for renaming directory/file.
        old_abspath = self.abspath
        # Save file path for any attached file.
        if self.has_file:
            old_abspathfile = self.abspathfile
        # Actually change the title of the note; rename the file/directory.
        self._title = title
        if os.path.isdir(old_abspath):
            abspath = self.abspath
            os.rename(old_abspath, abspath)
        else:
            abspath = self.abspath + ".md"
            os.rename(old_abspath + ".md", abspath)
        # Rename the attached file if there is one.
        if self.has_file:
            os.rename(old_abspathfile, self.abspathfile)
        # Force the modified timestamp of the file to now.
        self.set_modified()
        # Get the new path for each note whose path was changed.
        changed_paths = zip(old_paths, [note.path for note in changing])
        for note in linking:
            text = note.text
            for old_path, new_path in changed_paths:
                text = text.replace(f"[[{old_path}]]", f"[[{new_path}]]")
            note._text = text  # Do not add backlinks just yet.
            note._ast = None  # Force recompile of AST.
            note.write(update_modified=False)

    title = property(get_title, set_title, doc="The title of the note.")

    def get_text(self):
        return self._text

    def set_text(self, text):
        text = text.replace("\r", "")
        self.remove_backlinks()
        self.remove_hashtags()
        self.remove_attributes()
        self._text = text
        self._ast = None  # Force recompile of AST.
        self.add_backlinks()
        self.add_hashtags()
        self.add_attributes()
        self.write()

    text = property(
        get_text, set_text, doc="The text of the note using Markdown format."
    )

    def get_modified(self):
        if self.subnotes or self is ROOT:
            return os.path.getmtime(os.path.join(self.abspath, "__text__.md"))
        else:
            return os.path.getmtime(self.abspath + ".md")

    def set_modified(self, value=None):
        if value is None:
            value = time.time()
        if self.subnotes:
            os.utime(os.path.join(self.abspath, "__text__.md"), (value, value))
        else:
            os.utime(self.abspath + ".md", (value, value))

    modified = property(
        get_modified, set_modified, doc="The modification timestamp of the note."
    )

    @property
    def ast(self):
        "Set the private variable to None to force recompile of the AST."
        if self._ast is None:
            self._ast = get_md_ast_parser().convert(self.text)
        return self._ast

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
            return os.path.join(flask.current_app.config["SCRAPBOOK_DIRPATH"], path)
        else:
            return flask.current_app.config["SCRAPBOOK_DIRPATH"]

    @property
    def abspathfile(self):
        if not self.has_file:
            raise ValueError("No file attached to this note.")
        return self.abspath + self.file_extension

    @property
    def url(self):
        if self.path:
            return flask.url_for("note", path=self.path)
        else:
            return flask.url_for("home")

    @property
    def has_file(self):
        return bool(self.file_extension)

    @property
    def file_size(self):
        if not self.has_file:
            return 0
        return os.path.getsize(self.abspathfile)

    @property
    def has_image_file(self):
        if not self.has_file:
            return False
        return self.file_extension in flask.current_app.config["IMAGE_EXTENSIONS"]

    @property
    def has_text_file(self):
        if not self.has_file:
            return False
        return self.file_extension in flask.current_app.config["TEXT_EXTENSIONS"]

    @property
    def count(self):
        "Return the number of subnotes."
        return len(self.subnotes)

    @property
    def starred(self):
        "Is the note starred?"
        return self in STARRED

    def star(self, remove=False):
        "Toggle the star state of the note, or force remove."
        if self in STARRED:
            STARRED.remove(self)
        elif not remove:
            STARRED.add(self)
        else:
            return  # No change; no need to update file.
        filepath = os.path.join(
            flask.current_app.config["SCRAPBOOK_DIRPATH"], "__starred__.json"
        )
        with open(filepath, "w") as outfile:
            json.dump({"paths": [n.path for n in STARRED]}, outfile)

    def put_recent(self):
        "Put the note to the start of the list of recently modified notes."
        # Root note should not be listed.
        if self.supernote is None:
            return
        self.remove_recent()
        RECENT.appendleft(self)

    def remove_recent(self):
        "Remove this note from the list of recently modified notes."
        try:
            RECENT.remove(self)
        except ValueError:
            pass

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

    def siblings(self):
        """Return the list of sibling notes; subnotes for
        the supernote of this one, excluding itself.
        """
        if self.supernote:
            result = list(self.supernote.subnotes)
            result.remove(self)
        else:
            result = []
        return result

    def traverse(self):
        "Return a generator traversing this note and its subnotes."
        yield self
        for subnote in self.subnotes:
            yield from subnote.traverse()

    def write(self, update_modified=True):
        "Write this note to disk. Does *not* write subnotes."
        if os.path.isdir(self.abspath):
            abspath = os.path.join(self.abspath, "__text__.md")
            try:
                stat = os.stat(abspath)
            except OSError:  # Fallback to directory if no text file.
                stat = os.stat(self.abspath)
            with open(abspath, "w") as outfile:
                outfile.write(self.text)
        else:
            abspath = self.abspath + ".md"
            try:
                stat = os.stat(abspath)
            except OSError:  # If the note is new, then no such file.
                stat = None
            with open(abspath, "w") as outfile:
                outfile.write(self.text)
        if not update_modified and stat:
            os.utime(abspath, (stat.st_atime, stat.st_mtime))

    def upload_file(self, content, extension):
        """Upload the file given by content and filename extension.
        Does NOT change the modified timestamp, nor puts the note into
        the list of recently modified notes.
        NOTE: This is based on the assumption that the note was also
        modified in some other way in the same operation.
        """
        if self is ROOT:
            raise ValueError("Cannot attach a file to the root note.")
        extension = extension.lower()
        # Uploading Markdown files would create havoc.
        if extension == ".md":
            raise ValueError("Upload of '.md' files is not allowed.")
        # Non-extension upload must have some extension.
        elif not extension:
            extension = ".bin"
        # Remove any existing attached file; may have different extension
        if self.has_file:
            os.remove(self.abspathfile)
        filepath = os.path.join(self.supernote.abspath, self.title + extension)
        with open(filepath, "wb") as outfile:
            outfile.write(content)
        self.file_extension = extension

    def remove_file(self):
        "Remove the attached file, if any."
        if not self.has_file:
            return
        os.remove(self.abspathfile)
        self.file_extension = None

    def read(self):
        "Read this note and its subnotes from disk."
        if os.path.exists(self.abspath):
            # It's a directory with subnotes.
            try:
                filepath = os.path.join(self.abspath, "__text__.md")
                with open(filepath) as infile:
                    self._text = infile.read()
            except OSError:  # No text file for directory.
                self._text = ""
                # Fallback: Use directory's timestamp!
                stat = os.stat(self.abspath)
                # Create an empty text file.
                filepath = os.path.join(self.abspath, "__text__.md")
                with open(filepath, "w") as outfile:
                    outfile.write("")
                os.utime(filepath, (stat.st_atime, stat.st_mtime))
            self._ast = None  # Force recompile of AST.
            self._files = {}  # Needed only during read of subnotes.
            basenames = []
            for filename in sorted(os.listdir(self.abspath)):
                if filename.startswith("_"):
                    continue
                if filename.endswith("~"):
                    continue
                basename, extension = os.path.splitext(filename)
                # Note file; handle once directory listing is done.
                if not extension or extension == ".md":
                    basenames.append(basename)
                # Record attached files for later.
                else:
                    self._files[basename] = extension
            # Actually read subnotes when all files have been cycled over.
            for basename in basenames:
                note = Note(self, basename)
                note.read()
            # Create notes for all non-md files that are not yet attached.
            for title, extension in self._files.items():
                note = Note(self, title)
                note.file_extension = extension
                note.write()
            del self._files  # No longer needed.
        else:
            # It's a file; no subnotes.
            filepath = self.abspath + ".md"
            with open(filepath) as infile:
                self._text = infile.read()
                self._ast = None  # Force recompile of AST.
        # Both directory (except root) and file note may have
        # an attachment, which would be a single file at the
        # same level with the same name, but a non-md extension.
        if self.supernote:
            # Attached files recorded in supernote.
            try:
                self.file_extension = self.supernote._files.pop(self.title)
            except KeyError:
                pass

    def get_backlinks(self):
        "Get the notes linking to this note."
        return sorted(BACKLINKS.get(self, list()))

    def add_backlinks(self):
        "Add to the lookup the links in this note to other notes."
        for link in self.find_links(self.ast["children"]):
            try:
                note = get_note(link)
            except KeyError:  # Stale link.
                self.stale_links.append(link)
            else:
                BACKLINKS.setdefault(note, set()).add(self)

    def remove_backlinks(self):
        "Remove from the lookup the links in this note to other notes."
        for link in self.find_links(self.ast["children"]):
            try:
                note = get_note(link)
            except KeyError:  # Stale link.
                try:
                    self.stale_links.remove(link)
                except ValueError:
                    pass
            else:
                BACKLINKS[note].remove(self)

    def find_links(self, children):
        """Find the note links in the children of the AST tree.
        Return the set of paths for the notes linked to.
        """
        result = set()
        if isinstance(children, list):
            for child in children:
                if child.get("element") == "note_link":
                    result.add(child["ref"])
                try:
                    result.update(self.find_links(child["children"]))
                except KeyError:
                    pass
        return result

    def add_hashtags(self):
        "Add the hashtags in this note to the lookup."
        for word in self.find_hashtags(self.ast["children"]):
            HASHTAGS.setdefault(word, set()).add(self)

    def remove_hashtags(self):
        "Remove the hashtags in this note from the lookup."
        for word in self.find_hashtags(self.ast["children"]):
            HASHTAGS[word].remove(self)
            if not HASHTAGS[word]:  # Remove if empty.
                HASHTAGS.pop(word)

    def find_hashtags(self, children):
        """Find the hashtags in the children of the AST tree.
        Return the set of words.
        """
        result = set()
        if isinstance(children, list):
            for child in children:
                if child.get("element") == "hash_tag":
                    result.add(child["word"])
                try:
                    result.update(self.find_hashtags(child["children"]))
                except KeyError:
                    pass
        return result

    def add_attributes(self):
        """Add the attributes in this note to the lookup.
        Includes the hard-wired attribute 'File' when present.
        """
        attributes = list(self.find_attributes(self.ast["children"]).items())
        if self.file_extension:
            attributes.append(("File", [self.file_extension.strip(".")]))
            attributes.append(("File size", [self.file_size]))
        for key, values in attributes:
            attr = ATTRIBUTES.setdefault(key, dict())
            for value in values:
                attr.setdefault(value, set()).add(self)

    def remove_attributes(self):
        "Remove the attributes in this note from the lookup."
        attributes = list(self.find_attributes(self.ast["children"]).items())
        if self.file_extension:
            attributes.append(("File", [self.file_extension.strip(".")]))
            attributes.append(("File size", [self.file_size]))
        for key, values in attributes:
            attr = ATTRIBUTES[key]
            for value in values:
                attr[value].remove(self)
                if not attr[value]:  # Remove if empty.
                    attr.pop(value)
            if not ATTRIBUTES[key]:  # Remove if empty.
                ATTRIBUTES.pop(key)

    def find_attributes(self, children):
        """Find the attributes in the children of the AST tree.
        Return the lookup of keys to values.
        """
        result = dict()
        if isinstance(children, list):
            for child in children:
                if child.get("element") == "attribute":
                    attr = result.setdefault(child["key"], set())
                    attr.add(child["value"])
                try:
                    attrs = self.find_attributes(child["children"])
                except KeyError:
                    pass
                else:
                    for key, value in attrs.items():
                        result.setdefault(key, set()).update(value)
        return result

    def create_subnote(self, title, text):
        "Create and return a subnote."
        orig_title = cleanup_title(title)
        count = 1
        title = orig_title
        while True:
            for subnote in self.subnotes:
                if title == subnote.title:
                    count += 1
                    title = f"{orig_title}_{count}"
                    break
            else:
                break
        if title != orig_title:
            flash_warning(
                "The title was modified to make it unique" " among sibling notes."
            )
        # If this note is a file, then convert it into a directory.
        absfilepath = self.abspath + ".md"
        if os.path.isfile(absfilepath):
            os.mkdir(self.abspath)
            os.rename(absfilepath, os.path.join(self.abspath, "__text__.md"))
        note = Note(self, title)
        self.subnotes.sort()
        # Set the text of the subnote; this also adds any backlinks.
        note.text = text
        note.write()
        note.put_recent()
        return note

    def move(self, supernote):
        "Move this note to the given supernote."
        # The set of notes whose paths will change: this one and all below it.
        changing = list(self.traverse())
        if supernote in changing:
            raise ValueError("Cannot move note to itself or one of its subnotes.")
        for note in supernote.subnotes:
            if self.title == note.title:
                raise ValueError(
                    "New supernote already has a subnote"
                    " with the title of this note."
                )
        # Remember the old path for all notes whose paths will change.
        old_paths = [note.path for note in changing]
        # The set of notes which link to any of the changing-path notes.
        linking = set()
        for note in changing:
            linking.update(BACKLINKS.get(note, list()))
        # Old abspath needed for renaming directory/file.
        old_abspath = self.abspath
        # Save file path for any attached file.
        if self.has_file:
            old_abspathfile = self.abspathfile
        # If the new supernote is a file, then convert it first to a directory.
        super_absfilepath = supernote.abspath + ".md"
        if os.path.isfile(super_absfilepath):
            os.mkdir(supernote.abspath)
            os.rename(super_absfilepath, os.path.join(supernote.abspath, "__text__.md"))
        # Remember old supernote.
        old_supernote = self.supernote
        # Actually set the new supernote; move the file/directory of the note.
        old_supernote.subnotes.remove(self)
        self.supernote = supernote
        self.supernote.subnotes.append(self)
        self.supernote.subnotes.sort()
        if os.path.isdir(old_abspath):
            new_abspath = self.abspath
            os.rename(old_abspath, new_abspath)
        else:
            new_abspath = self.abspath + ".md"
            os.rename(old_abspath + ".md", new_abspath)
        # Move the attached file if there is one.
        if self.has_file:
            os.rename(old_abspathfile, self.abspathfile)
        # Convert the old supernote to file, if no subnotes left in it.
        if len(old_supernote.subnotes) == 0:
            os.rename(
                os.path.join(old_supernote.abspath, "__text__.md"),
                old_supernote.abspath + ".md",
            )
            os.rmdir(old_supernote.abspath)
        # Get the new path for each note whose path was changed.
        changed_paths = zip(old_paths, [note.path for note in changing])
        for note in linking:
            text = note.text
            for old_path, new_path in changed_paths:
                text = text.replace(f"[[{old_path}]]", f"[[{new_path}]]")
            note._text = text  # Do not add backlinks just yet.
            note._ast = None  # Force recompile.
            note.write(update_modified=False)
        # Force the modified timestamp of the file to now.
        self.set_modified()
        # Add this note to recently changed.
        self.put_recent()

    def is_deletable(self):
        """May this note be deleted?
        - Must have no subnotes.
        - Must have no links to it.
        """
        if self.supernote is None:
            return False
        if self.count:
            return False
        if self.get_backlinks():
            return False
        return True

    def delete(self):
        "Delete this note."
        if not self.is_deletable():
            raise ValueError("This note may not be deleted.")
        self.remove_backlinks()
        self.remove_hashtags()
        self.star(remove=True)
        self.remove_recent()
        os.remove(self.abspath + ".md")
        if self.has_file:
            os.remove(self.abspathfile)
        self.supernote.subnotes.remove(self)
        # Convert supernote to file if no subnotes any longer. Not root!
        if self.supernote.count == 0 and self.supernote is not None:
            abspath = self.supernote.abspath
            filepath = os.path.join(abspath, "__text__.md")
            try:
                os.rename(filepath, abspath + ".md")
            except OSError:  # May happen if e.g. no text for dir.
                with open(abspath + ".md", "w") as outfile:
                    outfile.write(sels.supernote.text)
            os.rmdir(abspath)

    def check_synced_filesystem(self):
        "When DEBUG: Check that this note is synced with its storage on disk."
        if not flask.current_app.config["DEBUG"]:
            return
        if self.subnotes or self is ROOT:
            if not os.path.isdir(self.abspath):
                raise RuntimeError(f"'{self}' contains subnotes but is not a directory")
            try:
                with open(os.path.join(self.abspath, "__text__.md")) as infile:
                    text = infile.read()
            except OSError:
                text = ""
        else:
            abspath = self.abspath + ".md"
            if not os.path.isfile(abspath):
                raise RuntimeError(f"{self} has no subnotes but is not a file")
            with open(abspath) as infile:
                text = infile.read()
        if text != self.text:
            raise RuntimeError(f"'{self}' text differs from file")


class Timer:
    "CPU timer, wall-clock timer."

    def __init__(self):
        self.cpu_start = time.process_time()
        self.wallclock_start = time.time()

    def __str__(self):
        return f"CPU time: {self.cpu_time:.3f} s, wall-clock time: {self.wallclock_time:.3f} s"

    @property
    def cpu_time(self):
        "Return CPU time (in seconds) since start of this timer."
        return time.process_time() - self.cpu_start

    @property
    def wallclock_time(self):
        "Return wall-clock time (in seconds) since start of this timer."
        return time.time() - self.wallclock_start


class NoteLink(marko.inline.InlineElement):
    "Link to another note."
    pattern = r"\[\[ *(.+?) *\]\]"
    parse_children = False

    def __init__(self, match):
        self.ref = match.group(1)


class NoteLinkRenderer:
    def render_note_link(self, element):
        try:
            note = get_note(element.ref)
        except KeyError:
            # Stale link; target does not exist.
            try:
                supernote, title = element.ref.rsplit("/", 1)
            except ValueError:
                supernote = None
                title = element.ref
            url = flask.url_for("create", supernote=supernote, title=title)
            return f' <a href="{url}" class="text-danger"' \
                ' title="Create a note for this stale link.">' \
                f'[[{element.ref}]]</a>'
        else:
            # Link to target.
            return f'<a class="fw-bold text-decoration-none" href="{note.url}">[[{note.title}]]</a>'


class HashTag(marko.inline.InlineElement):
    "Hashtag in the text of a note."
    pattern = r"#([^#].+?)\b"
    parse_children = False

    def __init__(self, match):
        self.word = match.group(1)


class HashTagRenderer:
    def render_hash_tag(self, element):
        url = flask.url_for("hashtag", word=element.word)
        return (
            f'<a href="{url}" class="fw-bold text-decoration-none">'
            f"#{element.word}</a>"
        )


class BareUrl(marko.inline.InlineElement):
    "A bare URL in the note text converted automatically to a link."
    pattern = r"(https?://\S+)"
    parse_children = False

    def __init__(self, match):
        self.url = match.group(1)


class BareUrlRenderer:
    def render_bare_url(self, element):
        return f'<a class="text-decoration-none" href="{element.url}">{element.url}</a>'


class Attribute(marko.inline.InlineElement):
    "An attribute specified in the text of a note."
    pattern = r"{([^:]+):([^}]*)}"
    parse_children = False

    def __init__(self, match):
        self.key = match.group(1).strip()
        self.value = match.group(2).strip()


class AttributeRenderer:
    def render_attribute(self, element):
        key_url = flask.url_for("attribute", key=element.key)
        value_url = flask.url_for(
            "attribute_value", key=element.key, value=element.value
        )
        return (
            f'<a href="{key_url}"'
            ' class="fw-bold text-success text-decoration-none">'
            f"{element.key}:</a>"
            f' <a href="{value_url}"'
            'class="text-success text-decoration-none">'
            f"{element.value}</a>"
        )


class Extensions:
    elements = [NoteLink, HashTag, BareUrl, Attribute]
    renderer_mixins = [
        NoteLinkRenderer,
        HashTagRenderer,
        BareUrlRenderer,
        AttributeRenderer,
    ]


class HTMLRenderer(marko.html_renderer.HTMLRenderer):
    "Fix output for Bootstrap."

    def render_quote(self, element):
        return '<blockquote class="blockquote">\n{}</blockquote>\n'.format(
            self.render_children(element)
        )


def get_md_parser():
    "Get the extended Markdown parser for HTML."
    return marko.Markdown(extensions=[Extensions], renderer=HTMLRenderer)


def get_md_ast_parser():
    "Get the extended Markdown parser for AST."
    return marko.Markdown(
        extensions=[Extensions], renderer=marko.ast_renderer.ASTRenderer
    )


def markdown(value):
    "Filter to process the value using augmented Marko markdown."
    return jinja2.utils.Markup(get_md_parser().convert(value or ""))


def localtime(value):
    "Filter to convert epoch value to local time ISO string."
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(value))


def flash_error(msg):
    flask.flash(str(msg), "error")


def flash_warning(msg):
    flask.flash(str(msg), "warning")


def flash_message(msg):
    flask.flash(str(msg), "message")


def cleanup_title(title):
    "Clean up the title; remove or replace bad characters."
    # Convert bad characters to underscore.
    # - Remove some particular offensive characters.
    # - Replace some other characters with blanks.
    # - Replace with underscore those bad for the OS filesystem.
    title = [
        c if c not in flask.current_app.config["BAD_CHARACTERS"] else "_" for c in title
    ]
    # Remove or replace some particular characters.
    title = [c for c in title if c not in "\a\b\r"]
    title = [c if c not in "\t\n" else " " for c in title]
    title = "".join(title)
    title = title.lstrip("_")  # Avoid confusion with 'scrapbooks' files.
    return title.strip()


def get_note(path):
    "Get the note given its path."
    if not path:
        return ROOT
    note = ROOT
    parts = list(reversed(path.split("/")))
    while parts:
        title = parts.pop()
        for subnote in note.subnotes:
            if title == subnote.title:
                note = subnote
                break
        else:
            raise KeyError(f"No such note '{path}'.")
    return note


def get_starred():
    return sorted(STARRED)


def get_recent():
    return list(RECENT)


def get_hashtags():
    return sorted(HASHTAGS.keys())


def get_attributes():
    return sorted(ATTRIBUTES.keys())


def check_recent_ordered():
    "When DEBUG: Check that RECENT is ordered."
    if not flask.current_app.config["DEBUG"]:
        return
    flask.current_app.logger.debug("checked_recent_ordered")
    if not RECENT:
        return
    latest = RECENT[0]
    for note in RECENT:
        if note.modified > latest.modified:
            content = "\n".join([f"{localtime(n.modified)}  {n}" for n in RECENT])
            raise RuntimeError(f"RECENT out of order:\n{content}")


def check_synced_filesystem():
    "When DEBUG: Check that all notes in memory exist as files/directories."
    if not flask.current_app.config["DEBUG"]:
        return
    flask.current_app.logger.debug("checked_synced_filesystem")
    for note in ROOT.traverse():
        note.check_synced_filesystem()


def check_synced_memory():
    "When DEBUG: Check that files/directories exist as notes in memory."
    if not flask.current_app.config["DEBUG"]:
        return
    flask.current_app.logger.debug("checked_synced_memory")
    root = flask.current_app.config["SCRAPBOOK_DIRPATH"]
    try:
        abspath = os.path.join(root, "__text__.md")
        with open(abspath) as infile:
            text = infile.read()
    except OSError:
        text = ""
    if text != ROOT.text:
        raise RuntimeError(f"file {abspath} text differs from ROOT")
    for dirpath, dirnames, filenames in os.walk(root):
        for dirname in dirnames:
            abspath = os.path.join(dirpath, dirname)
            path = abspath[len(root) + 1 :]
            try:
                note = get_note(path)
            except KeyError:
                raise RuntimeError(f"No note for directory {abspath}")
            if not note.subnotes:
                raise RuntimeError(f"Directory {abspath} note has no subnotes")
            try:
                textabspath = os.path.join(abspath, "__text__.md")
                with open(textabspath) as infile:
                    text = infile.read()
            except OSError:
                text = ""
            if text != note.text:
                raise RuntimeError(f"file {textabspath} text differs from '{note}'")

        for filename in filenames:
            abspath = os.path.join(dirpath, filename)
            basename, ext = os.path.splitext(filename)
            if basename.startswith("_"):
                continue
            path = os.path.join(dirpath, basename)[len(root) + 1 :]
            if ext == ".md":
                try:
                    note = get_note(path)
                except KeyError:
                    raise RuntimeError(f"No note for file {abspath}")
                with open(abspath) as infile:
                    text = infile.read()
                if text != note.text:
                    raise RuntimeError(f"file {abspath} text differs from '{note}'")
            else:
                try:
                    note = get_note(path)
                except KeyError:
                    raise RuntimeError(f"No note '{path}' for non-md file {abspath}")
                if ext != note.file_extension:
                    raise RuntimeError(
                        f"Non-md file {abspath} extension" f" does not match '{note}'"
                    )


def get_csrf_token():
    "Output HTML for cross-site request forgery (CSRF) protection."
    # Generate a token to last the session's lifetime.
    if "_csrf_token" not in flask.session:
        flask.session["_csrf_token"] = uuid.uuid4().hex
    html = (
        '<input type="hidden" name="_csrf_token" value="%s">'
        % flask.session["_csrf_token"]
    )
    return jinja2.utils.Markup(html)


def check_csrf_token():
    "Check the CSRF token for POST HTML."
    # Do not use up the token; keep it for the session's lifetime.
    token = flask.session.get("_csrf_token", None)
    if not token or token != flask.request.form.get("_csrf_token"):
        flask.abort(http.client.BAD_REQUEST)


def get_http_method():
    "Return the HTTP request method, taking tunneling into account."
    method = flask.request.method
    if method == "POST":
        check_csrf_token()
        try:
            method = flask.request.form["_http_method"]
        except KeyError:
            pass
    return method


app = flask.Flask(__name__)

app.add_template_filter(markdown)
app.add_template_filter(localtime)


@app.before_first_request
def setup():
    """Read all notes and keep in memory. Set up:
    - List of recent notes
    - List of starred notes
    - Set up map of backlinks
    - Set up map of hashtags
    """
    timer = Timer()
    global ROOT
    global RECENT
    STARRED.clear()
    BACKLINKS.clear()
    HASHTAGS.clear()
    ATTRIBUTES.clear()
    ROOT = Note(None, None)
    # Nothing more to do if no scrapbooks.
    if not flask.current_app.config["SCRAPBOOK_DIRPATH"]:
        return
    # Read in all notes.
    ROOT.read()
    # Set up most recently modified notes.
    traverser = ROOT.traverse()
    next(traverser)  # Skip root note.
    notes = list(traverser)
    notes.sort(key=lambda n: n.modified, reverse=True)
    RECENT = collections.deque(
        notes[: flask.current_app.config["MAX_RECENT"]],
        maxlen=flask.current_app.config["MAX_RECENT"],
    )
    # Get the starred notes.
    try:
        filepath = os.path.join(
            flask.current_app.config["SCRAPBOOK_DIRPATH"], "__starred__.json"
        )
        with open(filepath) as infile:
            for path in json.load(infile)["paths"]:
                try:
                    STARRED.add(get_note(path))
                except KeyError:
                    pass
    except OSError:
        pass
    # Set up the backlinks, hashtags and attributes for all notes.
    for note in ROOT.traverse():
        note.add_backlinks()
        note.add_hashtags()
        note.add_attributes()
    check_recent_ordered()
    check_synced_filesystem()
    check_synced_memory()
    flash_message(f"Setup {timer}")


@app.context_processor
def setup_template_context():
    "Add to the global context of Jinja2 templates."
    return dict(
        interactive=True,
        flash_error=flash_error,
        flash_warning=flash_warning,
        flash_message=flash_message,
        get_operations=get_operations,
        get_csrf_token=get_csrf_token,
        get_starred=get_starred,
        get_recent=get_recent,
        get_hashtags=get_hashtags,
        get_attributes=get_attributes,
    )


@app.route("/")
def home():
    "Home page; root note of the current scrapbook."
    if not flask.current_app.config["SCRAPBOOK_DIRPATH"]:
        return flask.redirect(flask.url_for("scrapbook"))
    n_links = sum([len(s) for s in BACKLINKS.values()])
    scrapbooks = [
        (os.path.basename(n), n) for n in flask.current_app.config["SCRAPBOOKS"]
    ]
    return flask.render_template(
        "home.html", root=ROOT, n_links=n_links, scrapbooks=scrapbooks
    )


@app.route("/note")
@app.route("/note/")
def root():
    "Root note of the current scrapbook; redirect to home."
    return flask.redirect(flask.url_for("home"))


@app.route("/create", methods=["GET", "POST"])
def create():
    """Create a new note, optionally with an uploaded file.
    Also used to create a copy of an existing note.
    """
    method = get_http_method()

    if method == "GET":
        try:
            supernote = get_note(flask.request.values["supernote"])
        except KeyError:
            supernote = None  # Root supernote.
        try:
            source = get_note(flask.request.values["source"])
            title = f"Copy of {source.title}"
            text = source.text
        except KeyError:
            source = None
            text = None
            try:
                title = flask.request.values["title"]
            except KeyError:
                title = None
        return flask.render_template(
            "create.html",
            supernote=supernote,
            title=title,
            text=text,
            cancel_url=flask.request.headers.get('referer')
        )

    elif method == "POST":
        try:
            superpath = flask.request.form["supernote"]
            if not superpath:
                raise KeyError
        except KeyError:
            supernote = ROOT
        else:
            try:
                supernote = get_note(superpath)
            except KeyError:
                flash_error(f"No such supernote: '{superpath}'")
                return flask.redirect(flask.url_for("home"))
        upload = flask.request.files.get("upload")
        if upload:
            title, extension = os.path.splitext(upload.filename)
        else:
            title = "No title"
        title = flask.request.form.get("title") or title
        text = flask.request.form.get("text") or ""
        try:
            note = supernote.create_subnote(title, text)
            if upload:
                note.upload_file(upload.read(), extension)
        except ValueError as error:
            flash_error(error)
            return flask.redirect(supernote.url)
        # Fix any stale links in other notes to this one.
        path = note.path
        for other in ROOT.traverse():
            if path in other.stale_links:
                print(f"fixing stale link '{path}'")
                BACKLINKS.setdefault(note, set()).add(other)
                other.stale_links.remove(path)
        check_recent_ordered()
        check_synced_filesystem()
        check_synced_memory()
        return flask.redirect(note.url)


@app.route("/note/<path:path>")
def note(path):
    "Display page for the given note."
    try:
        note = get_note(path)
    except KeyError:
        flash_error(f"No such note: '{path}'")
        return flask.redirect(flask.url_for("note", path=os.path.dirname(path)))
    print("stale links", note.stale_links)
    return flask.render_template("note.html", note=note)


@app.route("/file/<path:path>")
def file(path):
    "Return the file for the given note."
    try:
        note = get_note(path)
    except KeyError:
        flash_error(f"No such note: '{path}'")
        return flask.redirect(flask.url_for("note", path=os.path.dirname(path)))
    if not note.has_file:
        raise KeyError(f"No file attached to note '{path}'")
    return flask.send_file(note.abspathfile, conditional=False)


@app.route("/edit/", methods=["GET", "POST"])
@app.route("/edit/<path:path>", methods=["GET", "POST", "DELETE"])
def edit(path=""):
    "Edit the given note; title (i.e. file/directory rename) and/or text."
    try:
        note = get_note(path)
    except KeyError:
        if not path:
            note = ROOT
        else:
            flash_error(f"No such note: '{path}'")
            return flask.redirect(flask.url_for("note", path=os.path.dirname(path)))

    method = get_http_method()

    if method == "GET":
        return flask.render_template("edit.html", note=note)

    elif method == "POST":
        try:
            title = flask.request.form.get("title") or ""
            note.title = title
        except ValueError as error:
            flash_error(f"Invalid title: '{title}'")
            return flask.redirect(flask.url_for("edit", path=path))
        except KeyError as error:
            flash_error(f"Note already exists: '{title}'")
            return flask.redirect(flask.url_for("edit", path=path))
        # Actually change text; should update links, etc.
        note.text = flask.request.form.get("text") or ""
        # Handle file remove or upload.
        if flask.request.form.get("removefile"):
            note.remove_file()
        else:
            upload = flask.request.files.get("upload")
            if upload:
                note.upload_file(upload.read(), os.path.splitext(upload.filename)[1])
        note.put_recent()
        if note.stale_links:
            flash_warning("There are stale links in this note.")
        check_recent_ordered()
        check_synced_filesystem()
        check_synced_memory()
        return flask.redirect(note.url)

    elif method == "DELETE":
        try:
            note = get_note(path)
        except KeyError:
            flash_error(f"No such note: '{path}'")
            return flask.redirect(flask.url_for("note", path=os.path.dirname(path)))
        try:
            note.delete()
        except ValueError as error:
            flash_error(error)
            return flask.redirect(note.url)
        check_recent_ordered()
        check_synced_filesystem()
        check_synced_memory()
        return flask.redirect(note.supernote.url)


@app.route("/op/<name>/<path:path>", methods=["POST"])
def operation(name, path):
    get_http_method()  # Does CSRF check.
    try:
        note = get_note(path)
    except KeyError:
        flash_error(f"No such note: '{path}'")
        return flask.redirect(flask.url_for("note", path=os.path.dirname(path)))
    try:
        op = OPERATIONS[name]
    except KeyError:
        flash_error(f"No such operation: '{name}'")
        return flask.redirect(flask.url_for("note", path=path))
    try:
        if not op.is_relevant(note):
            raise ValueError("The operation is not relevant for this note.")
        op.execute(note, flask.request.form)
        note.put_recent()
    except ValueError as error:
        flash_error(error)
    check_recent_ordered()
    return flask.redirect(flask.url_for("note", path=path))


@app.route("/move/<path:path>", methods=["GET", "POST"])
def move(path):
    "Move the given note to a new supernote."
    try:
        note = get_note(path)
    except KeyError:
        flash_error(f"No such note: '{path}'")
        return flask.redirect(flask.url_for("note", path=os.path.dirname(path)))

    method = get_http_method()

    if method == "GET":
        if note is ROOT:
            flash_error("Cannot move root note.")
            return flask.redirect(note.url)
        return flask.render_template("move.html", note=note)

    elif method == "POST":
        supernote = flask.request.form.get("supernote") or ""
        if supernote.startswith("[["):
            supernote = supernote[2:]
        if supernote.endswith("]]"):
            supernote = supernote[:-2]
        try:
            supernote = get_note(supernote)
        except KeyError:
            flash_error(f"No such supernote: '{supernote}'")
        try:
            note.move(supernote)
        except ValueError as error:
            flash_error(error)
        check_recent_ordered()
        check_synced_filesystem()
        check_synced_memory()
        return flask.redirect(note.url)


@app.route("/star/<path:path>", methods=["POST"])
def star(path):
    "Toggle the star state of the note for the path."
    get_http_method()  # Does CSRF check.
    try:
        note = get_note(path)
    except KeyError:
        flash_error(f"No such note: '{path}'")
        return flask.redirect(flask.url_for("note", path=os.path.dirname(path)))
    note.star()
    return flask.redirect(note.url)


@app.route("/hashtag/<word>")
def hashtag(word):
    return flask.render_template(
        "hashtag.html", word=word, notes=sorted(HASHTAGS.get(word, list()))
    )


@app.route("/attribute/<key>")
def attribute(key):
    values = sorted([(k, sorted(v)) for k, v in ATTRIBUTES.get(key, dict()).items()])
    return flask.render_template("attribute.html", key=key, values=values)


@app.route("/attribute/<key>/<path:value>")
def attribute_value(key, value):
    notes = sorted(ATTRIBUTES.get(key, dict()).get(value))
    return flask.render_template(
        "attribute_value.html", key=key, value=value, notes=notes
    )


@app.route("/search")
def search():
    terms = flask.request.values.get("terms") or ""
    if terms:
        terms = terms.strip()
        if (terms[0] == '"' and terms[-1] == '"') or (
            terms[0] == "'" and terms[-1] == "'"
        ):
            terms = [terms[1:-1]]  # Quoted term; search as a whole
        else:
            terms = terms.split()
        terms.sort(key=lambda t: len(t), reverse=True)
        notes = []
        traverser = ROOT.traverse()
        next(traverser)  # Skip root note.
        timer = Timer()
        for note in traverser:
            for term in terms:
                if term not in note:
                    break
            else:
                notes.append(note)
        flash_message(f"Search {timer}")
    else:
        notes = []
    return flask.render_template(
        "search.html", notes=sorted(notes), terms=flask.request.values.get("terms")
    )


@app.route("/scrapbook", methods=["GET", "POST", "DELETE"])
def scrapbook():
    "Add a new scrapbook and switch to it. Or delete the current scrapbook."
    method = get_http_method()

    if method == "GET":
        return flask.render_template("scrapbook.html")

    elif method == "POST":
        try:
            try:
                dirpath = flask.request.form["scrapbook"]
                if not dirpath:
                    raise KeyError
            except KeyError:
                raise ValueError("No path given.")
            dirpath = os.path.expanduser(dirpath)
            dirpath = os.path.expandvars(dirpath)
            dirpath = os.path.normpath(dirpath)
            if not os.path.isabs(dirpath):
                dirpath = os.path.join(os.path.expanduser("~"), dirpath)
            # If the scrapbook already exists, no need to do anything.
            if dirpath in flask.current_app.config["SCRAPBOOKS"]:
                pass
            # Directory exists; add it as a scrapbook and go to it.
            elif os.path.isdir(dirpath):
                if not (os.access(dirpath, os.R_OK) and os.access(dirpath, os.W_OK)):
                    raise ValueError(f"No read/write access to '{dirpath}'")
                else:
                    flask.current_app.config["SCRAPBOOKS"].append(dirpath)
                    write_settings()
            # The path is a file; not allowed.
            elif os.path.isfile(dirpath):
                raise ValueError(f"'{dirpath}' is a file.")
            # The path  does not exist; create it.
            else:
                try:
                    os.mkdir(dirpath)
                except OSError as error:
                    raise ValueError(str(error))
                flash_message(
                    "Added scrapbook and created" f" the directory '{dirpath}'"
                )
                flask.current_app.config["SCRAPBOOKS"].append(dirpath)
                write_settings()
        except ValueError as error:
            flash_error(error)
            return flask.redirect(flask.url_for("home"))
        return change_scrapbook(dirpath)

    elif method == "DELETE":
        flask.current_app.config["SCRAPBOOKS"].pop(0)
        write_settings()
        try:
            scrapbook = flask.current_app.config["SCRAPBOOKS"][0]
        except IndexError:
            flask.current_app.config["SCRAPBOOK_DIRPATH"] = None
            flask.current_app.config["SCRAPBOOK_TITLE"] = None
            setup()
            return flask.redirect(flask.url_for("home"))
        else:
            return change_scrapbook(scrapbook)


@app.route("/scrapbook/<title>")
def switch_scrapbook(title):
    "Switch to another scrapbook. Yes, using GET for this is arguably bad."
    for scrapbook in flask.current_app.config["SCRAPBOOKS"]:
        if title == os.path.basename(scrapbook):
            break
    else:
        flash_error(f"No such scrapbook '{title}'.")
        return flask.redirect(flask.url_for("home"))
    return change_scrapbook(scrapbook)


def change_scrapbook(scrapbook):
    "Change to the given scrapbook."
    # Move to the top of the list.
    flask.current_app.config["SCRAPBOOKS"].remove(scrapbook)
    flask.current_app.config["SCRAPBOOKS"].insert(0, scrapbook)
    flask.current_app.config["SCRAPBOOK_DIRPATH"] = scrapbook
    flask.current_app.config["SCRAPBOOK_TITLE"] = os.path.basename(scrapbook)
    write_settings()
    setup()
    return flask.redirect(flask.url_for("home"))


if __name__ == "__main__":
    settings = get_settings()
    app.config.from_mapping(settings)
    load_operations(app)
    app.run(debug=settings["DEBUG"])
