"""Create a lot of random-content files in subdirectory 'notes/tmp'."""

import os
import os.path
import random
import string

MAX_NDIRS = 10
MAX_NFILES = 16
MAX_NCHARS = 250
WORD_CHARS = string.digits + string.ascii_letters + " "*20

def create(dirpath, level):
    print(f"Creating files in {dirpath}...")
    for nfile in range(random.randint(1, MAX_NFILES)):
        filename = ''.join(random.choices(string.ascii_letters, k=10))
        with open(os.path.join(dirpath, f"{filename}.md"), "w") as outfile:
            nchars = random.randint(1, MAX_NCHARS)
            outfile.write(''.join(random.choices(WORD_CHARS, k=nchars)))
    if level == 0: return
    for ndir in range(random.randint(1, MAX_NDIRS)):
        dirname = ''.join(random.choices(string.ascii_letters, k=10))
        subdirpath = os.path.join(dirpath, dirname)
        os.mkdir(subdirpath)
        create(subdirpath, level-1)


if __name__ == "__main__":
    random.seed(1234)
    dirpath = os.path.join(os.getcwd(), "notes/tmp")
    os.mkdir(dirpath)
    create(dirpath, 2)
