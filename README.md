# notebooks

Simple app for personal notes in your file system using your browser
as interface. Inspired by Obsidian.

## Features

- Each note is a single file.
- No separate database; the directory structure is the storage.
- Markdown for note text formatting.
- Links in the note text; backlinks between notes updated dynamically.
- Hashtags in note text.
- Search all titles and text.
- Hierarchic structure allowed; subnotes.
- Files of any kind may be stored.
- The app is a Flask server, so your browser is the interface for 
  navigation and editing.
- Keep separate notebooks (sets of notes) which can easily be switched between.

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

