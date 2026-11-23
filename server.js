"use strict";
// One command starts the supplied Flask backend and all website pages.
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const local=path.join(__dirname,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const python=process.env.TRINGGG_PYTHON || (fs.existsSync(local)?local:'python');
const child=spawn(python,[path.join(__dirname,'backend/run.py')],{stdio:'inherit',cwd:__dirname,windowsHide:true});
child.on('error',error=>{console.error('Cannot start Python. See README.txt for backend setup.',error.message);process.exitCode=1;});
child.on('exit',code=>{process.exitCode=code || 0;});
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>child.kill());
