<h1 align="center">👀IDA Object Viewer👀</h1>
<p>Graphical object viewer for IDA Pro.</p>

## What's IDAObjectViewer?
Graphical object viewer 

## Requirements

No dependencies.

## Installation

Put ```ida_object_viewer.py``` into plugins directory.

## Settings

Directly change param in ida_object_viewer.py
+ max_depth : how many (default=5) 
+ omit_loop : omit node if pointer loop detected.(default=True)

## Usage

Right click on the value then click "Open Object viewer".

+ TODO : gif image

## TODO

avoid collision and adjust the layout automatically
import color setting from IDA.
add double click action (goto address)

hanle
normal struct
list
pointer
pointer to struct
struct inside struct
struct list
enum
bit field param
union
variable length list
variable on the stack.