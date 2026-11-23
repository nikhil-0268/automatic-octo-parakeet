"""Start the complete local application: website and API on the same address."""
import os
from pathlib import Path
from app import create_app
from web import attach

data=Path(__file__).resolve().parent.parent/'data'
data.mkdir(exist_ok=True)
app=create_app(os.environ.get('TRINGGG_DB',str(data/'backend.sqlite')))
attach(app)
if __name__=='__main__':
    app.run(host='127.0.0.1',port=int(os.environ.get('PORT','3000')),debug=False)
