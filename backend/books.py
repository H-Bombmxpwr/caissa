"""Owned PDF copies, stored inside the portable library."""
import base64
import os
import time
import uuid


class Books:
    def __init__(self, library):
        self.library = library
        with library.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT NOT NULL DEFAULT '',
                filename TEXT NOT NULL, added_at INTEGER NOT NULL, page INTEGER NOT NULL DEFAULT 1)''')

    def list(self):
        return [dict(r) for r in self.library.connect().execute('SELECT * FROM books ORDER BY title COLLATE NOCASE')]

    def add(self, body):
        title=str(body.get('title','')).strip()[:250]
        if not title:
            raise ValueError('Give the book a title')
        encoded=body.get('data','')
        if len(encoded)>180*1024*1024:
            raise ValueError('PDFs must be smaller than 128 MB')
        data=base64.b64decode(encoded,validate=True)
        if not data.startswith(b'%PDF-') or len(data)>128*1024*1024:
            raise ValueError('Choose a PDF smaller than 128 MB')
        folder=os.path.join(self.library.dir,'books')
        os.makedirs(folder,exist_ok=True)
        filename=uuid.uuid4().hex+'.pdf'
        path=os.path.join(folder,filename)
        try:
            with open(path,'xb') as handle:
                handle.write(data)
            with self.library._write_lock,self.library.connect() as db:
                ident=db.execute('INSERT INTO books(title,author,filename,added_at) VALUES(?,?,?,?)',
                    (title,str(body.get('author','')).strip()[:250],filename,int(time.time()))).lastrowid
            return {'id':ident}
        except Exception:
            if os.path.isfile(path):
                os.remove(path)
            raise

    def file(self, ident):
        row=self.library.connect().execute('SELECT * FROM books WHERE id=?',(int(ident),)).fetchone()
        if not row:
            raise ValueError('Book not found')
        path=os.path.realpath(os.path.join(self.library.dir,'books',row['filename']))
        root=os.path.realpath(os.path.join(self.library.dir,'books'))
        if os.path.commonpath([root,path])!=root or not os.path.isfile(path):
            raise ValueError('PDF file is missing')
        return path

    def update(self, ident, body):
        page=max(1,min(100000,int(body.get('page',1))))
        with self.library._write_lock,self.library.connect() as db:
            if not db.execute('UPDATE books SET page=? WHERE id=?',(page,int(ident))).rowcount:
                raise ValueError('Book not found')
        return {'saved':True}
