<h1 align="center">👀IDA Object Viewer👀</h1>
<p>Graphical object viewer for IDA Pro.</p>

## What's IDAObjectViewer?
Graphical object viewer 

## Requirements

### Qt.py

```pip install Qt.py```

or

Put [Qt.py](https://raw.githubusercontent.com/mottosso/Qt.py/master/Qt.py) into ```$PYTHONPATH``` or IDA plugins directory.

### Notz

It will be cloned automatically.

## Installation

```
git clone --recursive https://github.com/Ga-ryo/IDAObjectViewer 
```

Put ```ida_object_viewer.py``` and ```Nodz``` directory into plugins directory.

## Settings

Directly change param in ida_object_viewer.py
+ max_depth : how many (default=5) 
+ omit_loop : omit node if pointer loop detected.(default=True)

## Usage

Right click on the value then click "Open Object viewer".

+ TODO : gif image