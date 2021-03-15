# scrapbooks

Simple app for personal notes, optionally with attached files, in the local
file system using a browser as interface.

## Features

- Each note is a single Markdown file.
- No separate database; a directory in the local file system is the storage.
- Links in the note text; backlinks between notes updated dynamically.
- Hashtags in note text.
- Attributes (key-value pairs) in the note text.
- Search all titles and text.
- Hierarchic structure of subnotes allowed. Maps directly to hierarchical
  directories.
- A file of any kind may be stored as an attachment to a note.
- The app is a `Flask` server, so your browser is the interface for 
  navigation and editing.
- Keep separate scrapbooks (sets of notes; separate directories) which can
  easily be switched between.
- Operations interface to add functionality. Current operations:
  - Image Optical Character Recognition (OCR) using `pytesseract`.
  - Image EXIF tags extraction using `Pillow`.

## Future features

- Inclusion of other note's text in a note.
- Publish using GitHub pages.
- Create MS Word file.
- Create PDF file.

## Implementation

Written in Python 3.6.

- The entire dataset is read and parsed on startup.
- The modification date of note files is kept unchanged when
  fixing backlinks after title edit or note move.

Third-party software:

- [Flask](https://flask.palletsprojects.com/en/1.1.x/)
- [Marko](https://github.com/frostming/marko)
- [Bootstrap 5](https://getbootstrap.com/docs/5.0/getting-started/introduction/)
- [clipboard.js](https://clipboardjs.com/)
- [pytesseract](https://pypi.org/project/pytesseract/)
- [Pillow](https://pypi.org/project/Pillow/)
