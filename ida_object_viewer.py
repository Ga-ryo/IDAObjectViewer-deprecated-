from PyQt5 import QtGui, QtCore, QtWidgets
import struct
import idaapi
import ida_kernwin
import idc
import idautils
import re

nodz = None
max_depth = 2 #TEMP
#TODO hook debugger activate event?
dbg_active = False
"""
struct struc_1 -> struc_1
struc_1 ->  struc_1
"""
pattern = '^[ ]*(struct[ ]+)?'
pat = re.compile(pattern)
bits = 0
endian = 'little'


############################################################################################################################
##############################################   nodz_util.py   ############################################################
############################################################################################################################

def convertDataToColor(data=None, alternate=False, av=20):
    """
    Convert a list of 3 (rgb) or 4(rgba) values from the configuration
    file into a QColor.

    :param data: Input color.
    :type  data: List.

    :param alternate: Whether or not this is an alternate color.
    :type  alternate: Bool.

    :param av: Alternate value.
    :type  av: Int.

    """
    # rgb
    if len(data) == 3:
        color = QtGui.QColor(data[0], data[1], data[2])
        if alternate:
            mult = generateAlternateColorMultiplier(color, av)


            color = QtGui.QColor(data[0]-(av*mult), data[1]-(av*mult), data[2]-(av*mult))
        return color

    # rgba
    elif len(data) == 4:
        color = QtGui.QColor(data[0], data[1], data[2], data[3])
        if alternate:
            mult = generateAlternateColorMultiplier(color, av)
            color = QtGui.QColor(data[0]-(av*mult), data[1]-(av*mult), data[2]-(av*mult), data[3])
        return color

    # wrong
    else:
        print 'Color from configuration is not recognized : ', data
        print 'Can only be [R, G, B] or [R, G, B, A]'
        print 'Using default color !'
        color = QtGui.QColor(120, 120, 120)
        if alternate:
            color = QtGui.QColor(120-av, 120-av, 120-av)
        return color

def generateAlternateColorMultiplier(color, av):
    """
    Generate a multiplier based on the input color lighness to increase
    the alternate value for dark color or reduce it for bright colors.

    :param color: Input color.
    :type  color: QColor.

    :param av: Alternate value.
    :type  av: Int.

    """
    lightness = color.lightness()
    mult = float(lightness)/255

    return mult

def createPointerBoundingBox(pointerPos, bbSize):
    """
    generate a bounding box around the pointer.

    :param pointerPos: Pointer position.
    :type  pointerPos: QPoint.

    :param bbSize: Width and Height of the bounding box.
    :type  bbSize: Int.

    """
    # Create pointer's bounding box.
    point = pointerPos

    mbbPos = point
    point.setX(point.x() - bbSize / 2)
    point.setY(point.y() - bbSize / 2)

    size = QtCore.QSize(bbSize, bbSize)
    bb = QtCore.QRect(mbbPos, size)
    bb = QtCore.QRectF(bb)

    return bb

def swapListIndices(inputList, oldIndex, newIndex):
    """
    Simply swap 2 indices in a the specified list.

    :param inputList: List that contains the elements to swap.
    :type  inputList: List.

    :param oldIndex: Index of the element to move.
    :type  oldIndex: Int.

    :param newIndex: Destination index of the element.
    :type  newIndex: Int.

    """
    if oldIndex == -1:
        oldIndex = len(inputList)-1


    if newIndex == -1:
        newIndex = len(inputList)

    value = inputList[oldIndex]
    inputList.pop(oldIndex)
    inputList.insert(newIndex, value)

############################################################################################################################
############################################################################################################################
############################################################################################################################


############################################################################################################################
##############################################   nodz_main.py   ############################################################
############################################################################################################################

class Nodz(QtWidgets.QGraphicsView):

    """
    The main view for the node graph representation.

    The node view implements a state pattern to control all the
    different user interactions.

    """

    signal_NodeCreated = QtCore.pyqtSignal(object)
    signal_NodeDeleted = QtCore.pyqtSignal(object)
    signal_NodeEdited = QtCore.pyqtSignal(object, object)
    signal_NodeSelected = QtCore.pyqtSignal(object)
    signal_NodeMoved = QtCore.pyqtSignal(str, object)

    signal_AttrCreated = QtCore.pyqtSignal(object, object)
    signal_AttrDeleted = QtCore.pyqtSignal(object, object)
    signal_AttrEdited = QtCore.pyqtSignal(object, object, object)

    signal_PlugConnected = QtCore.pyqtSignal(object, object, object, object)
    signal_PlugDisconnected = QtCore.pyqtSignal(object, object, object, object)
    signal_SocketConnected = QtCore.pyqtSignal(object, object, object, object)
    signal_SocketDisconnected = QtCore.pyqtSignal(object, object, object, object)

    signal_GraphSaved = QtCore.pyqtSignal()
    signal_GraphLoaded = QtCore.pyqtSignal()
    signal_GraphCleared = QtCore.pyqtSignal()
    signal_GraphEvaluated = QtCore.pyqtSignal()

    signal_KeyPressed = QtCore.pyqtSignal(object)
    signal_Dropped = QtCore.pyqtSignal()

    def __init__(self, parent, config_s):
        """
        Initialize the graphics view.

        """
        super(Nodz, self).__init__(parent)

        # Load nodz configuration.
        self.loadConfig(config_s)

        # General data.
        self.gridVisToggle = True
        self.gridSnapToggle = False
        self._nodeSnap = False
        self.selectedNodes = None

        # Connections data.
        self.drawingConnection = False
        self.currentHoveredNode = None
        self.sourceSlot = None

        # Display options.
        self.currentState = 'DEFAULT'
        self.pressedKeys = list()
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)

    def wheelEvent(self, event):
        """
        Zoom in the view with the mouse wheel.

        """
        self.currentState = 'ZOOM_VIEW'
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)

        inFactor = 1.15
        outFactor = 1 / inFactor

        if event.delta() > 0:
            zoomFactor = inFactor
        else:
            zoomFactor = outFactor

        self.scale(zoomFactor, zoomFactor)
        self.currentState = 'DEFAULT'

    def mousePressEvent(self, event):
        """
        Initialize tablet zoom, drag canvas and the selection.

        """
        # Tablet zoom
        if (event.button() == QtCore.Qt.RightButton and
            event.modifiers() == QtCore.Qt.AltModifier):
            self.currentState = 'ZOOM_VIEW'
            self.initMousePos = event.pos()
            self.zoomInitialPos = event.pos()
            self.initMouse = QtGui.QCursor.pos()
            self.setInteractive(False)


        # Drag view
        elif (event.button() == QtCore.Qt.MiddleButton and
              event.modifiers() == QtCore.Qt.AltModifier):
            self.currentState = 'DRAG_VIEW'
            self.prevPos = event.pos()
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            self.setInteractive(False)


        # Rubber band selection
        elif (event.button() == QtCore.Qt.LeftButton and
              event.modifiers() == QtCore.Qt.NoModifier and
              self.scene().itemAt(self.mapToScene(event.pos()), QtGui.QTransform()) is None):
            self.currentState = 'DRAG_WINDOW'
            #self._initRubberband(event.pos())
            self.setInteractive(False)


        # Drag Item
        elif (event.button() == QtCore.Qt.LeftButton and
              event.modifiers() == QtCore.Qt.NoModifier and
              self.scene().itemAt(self.mapToScene(event.pos()), QtGui.QTransform()) is not None):
            self.currentState = 'DRAG_ITEM'
            self.setInteractive(True)


        # Add selection
        elif (event.button() == QtCore.Qt.LeftButton and
              QtCore.Qt.Key_Shift in self.pressedKeys and
              QtCore.Qt.Key_Control in self.pressedKeys):
            self.currentState = 'ADD_SELECTION'
            self._initRubberband(event.pos())
            self.setInteractive(False)


        # Subtract selection
        elif (event.button() == QtCore.Qt.LeftButton and
              event.modifiers() == QtCore.Qt.ControlModifier):
            self.currentState = 'SUBTRACT_SELECTION'
            self._initRubberband(event.pos())
            self.setInteractive(False)


        # Toggle selection
        elif (event.button() == QtCore.Qt.LeftButton and
              event.modifiers() == QtCore.Qt.ShiftModifier):
            self.currentState = 'TOGGLE_SELECTION'
            self._initRubberband(event.pos())
            self.setInteractive(False)


        else:
            self.currentState = 'DEFAULT'

        super(Nodz, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """
        Update tablet zoom, canvas dragging and selection.

        """
        # Zoom.
        if self.currentState == 'ZOOM_VIEW':
            offset = self.zoomInitialPos.x() - event.pos().x()

            if offset > self.previousMouseOffset:
                self.previousMouseOffset = offset
                self.zoomDirection = -1
                self.zoomIncr -= 1

            elif offset == self.previousMouseOffset:
                self.previousMouseOffset = offset
                if self.zoomDirection == -1:
                    self.zoomDirection = -1
                else:
                    self.zoomDirection = 1

            else:
                self.previousMouseOffset = offset
                self.zoomDirection = 1
                self.zoomIncr += 1

            if self.zoomDirection == 1:
                zoomFactor = 1.03
            else:
                zoomFactor = 1 / 1.03

            # Perform zoom and re-center on initial click position.
            pBefore = self.mapToScene(self.initMousePos)
            self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)
            self.scale(zoomFactor, zoomFactor)
            pAfter = self.mapToScene(self.initMousePos)
            diff = pAfter - pBefore

            self.setTransformationAnchor(QtWidgets.QGraphicsView.NoAnchor)
            self.translate(diff.x(), diff.y())

        # Drag canvas.
        elif self.currentState == 'DRAG_VIEW':
            offset = self.prevPos - event.pos()
            self.prevPos = event.pos()
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + offset.y())
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + offset.x())

        # RuberBand selection.
        elif (self.currentState == 'SELECTION' or
              self.currentState == 'ADD_SELECTION' or
              self.currentState == 'SUBTRACT_SELECTION' or
              self.currentState == 'TOGGLE_SELECTION'):
            self.rubberband.setGeometry(QtCore.QRect(self.origin, event.pos()).normalized())

        super(Nodz, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """
        Apply tablet zoom, dragging and selection.

        """
        # Zoom the View.
        if self.currentState == '.ZOOM_VIEW':
            self.offset = 0
            self.zoomDirection = 0
            self.zoomIncr = 0
            self.setInteractive(True)


        # Drag View.
        elif self.currentState == 'DRAG_VIEW':
            self.setCursor(QtCore.Qt.ArrowCursor)
            self.setInteractive(True)

        elif self.currentState == 'DRAG_WINDOW':
            self.setInteractive(True)

        # Selection.
        elif self.currentState == 'SELECTION':
            self.rubberband.setGeometry(QtCore.QRect(self.origin,
                                                     event.pos()).normalized())
            painterPath = self._releaseRubberband()
            self.setInteractive(True)
            self.scene().setSelectionArea(painterPath)


        # Add Selection.
        elif self.currentState == 'ADD_SELECTION':
            self.rubberband.setGeometry(QtCore.QRect(self.origin,
                                                     event.pos()).normalized())
            painterPath = self._releaseRubberband()
            self.setInteractive(True)
            for item in self.scene().items(painterPath):
                item.setSelected(True)


        # Subtract Selection.
        elif self.currentState == 'SUBTRACT_SELECTION':
            self.rubberband.setGeometry(QtCore.QRect(self.origin,
                                                     event.pos()).normalized())
            painterPath = self._releaseRubberband()
            self.setInteractive(True)
            for item in self.scene().items(painterPath):
                item.setSelected(False)


        # Toggle Selection
        elif self.currentState == 'TOGGLE_SELECTION':
            self.rubberband.setGeometry(QtCore.QRect(self.origin,
                                                     event.pos()).normalized())
            painterPath = self._releaseRubberband()
            self.setInteractive(True)
            for item in self.scene().items(painterPath):
                if item.isSelected():
                    item.setSelected(False)
                else:
                    item.setSelected(True)

        self.currentState = 'DEFAULT'

        super(Nodz, self).mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        """
        Save pressed key and apply shortcuts.

        Shortcuts are:
        DEL - Delete the selected nodes
        F - Focus view on the selection

        """
        if event.key() not in self.pressedKeys:
            self.pressedKeys.append(event.key())

        if event.key() == QtCore.Qt.Key_Delete:
            self._deleteSelectedNodes()

        if event.key() == QtCore.Qt.Key_F:
            self._focus()

        if event.key() == QtCore.Qt.Key_S:
            self._nodeSnap = True

        # Emit signal.
        self.signal_KeyPressed.emit(event.key())

    def keyReleaseEvent(self, event):
        """
        Clear the key from the pressed key list.

        """
        if event.key() == QtCore.Qt.Key_S:
            self._nodeSnap = False

        if event.key() in self.pressedKeys:
            self.pressedKeys.remove(event.key())

    def _initRubberband(self, position):
        """
        Initialize the rubber band at the given position.

        """
        self.rubberBandStart = position
        self.origin = position
        self.rubberband.setGeometry(QtCore.QRect(self.origin, QtCore.QSize()))
        self.rubberband.show()

    def _releaseRubberband(self):
        """
        Hide the rubber band and return the path.

        """
        painterPath = QtGui.QPainterPath()
        rect = self.mapToScene(self.rubberband.geometry())
        painterPath.addPolygon(rect)
        self.rubberband.hide()
        return painterPath

    def _focus(self):
        """
        Center on selected nodes or all of them if no active selection.

        """
        if self.scene().selectedItems():
            itemsArea = self._getSelectionBoundingbox()
            self.fitInView(itemsArea, QtCore.Qt.KeepAspectRatio)
        else:
            itemsArea = self.scene().itemsBoundingRect()
            self.fitInView(itemsArea, QtCore.Qt.KeepAspectRatio)

    def _getSelectionBoundingbox(self):
        """
        Return the bounding box of the selection.

        """
        bbx_min = None
        bbx_max = None
        bby_min = None
        bby_max = None
        bbw = 0
        bbh = 0
        for item in self.scene().selectedItems():
            pos = item.scenePos()
            x = pos.x()
            y = pos.y()
            w = x + item.boundingRect().width()
            h = y + item.boundingRect().height()

            # bbx min
            if bbx_min is None:
                bbx_min = x
            elif x < bbx_min:
                bbx_min = x
            # end if

            # bbx max
            if bbx_max is None:
                bbx_max = w
            elif w > bbx_max:
                bbx_max = w
            # end if

            # bby min
            if bby_min is None:
                bby_min = y
            elif y < bby_min:
                bby_min = y
            # end if

            # bby max
            if bby_max is None:
                bby_max = h
            elif h > bby_max:
                bby_max = h
            # end if
        # end if
        bbw = bbx_max - bbx_min
        bbh = bby_max - bby_min
        return QtCore.QRectF(QtCore.QRect(bbx_min, bby_min, bbw, bbh))

    def _deleteSelectedNodes(self):
        """
        Delete selected nodes.

        """
        selected_nodes = list()
        for node in self.scene().selectedItems():
            selected_nodes.append(node.name)
            node._remove()

        # Emit signal.
        self.signal_NodeDeleted.emit(selected_nodes)

    def _returnSelection(self):
        """
        Wrapper to return selected items.

        """
        selected_nodes = list()
        if self.scene().selectedItems():
            for node in self.scene().selectedItems():
                selected_nodes.append(node.name)

        # Emit signal.
        self.signal_NodeSelected.emit(selected_nodes)


    ##################################################################
    # API
    ##################################################################

    def loadConfig(self, d):
        """
        Set a specific configuration for this instance of Nodz.

        :type  filePath: str.
        :param filePath: The path to the config file that you want to
                         use.

        """
        self.config = d

    def initialize(self):
        """
        Setup the view's behavior.

        """
        # Setup view.
        config = self.config
        self.setRenderHint(QtGui.QPainter.Antialiasing, config['antialiasing'])
        self.setRenderHint(QtGui.QPainter.TextAntialiasing, config['antialiasing'])
        self.setRenderHint(QtGui.QPainter.HighQualityAntialiasing, config['antialiasing_boost'])
        self.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, config['smooth_pixmap'])
        self.setRenderHint(QtGui.QPainter.NonCosmeticDefaultPen, True)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.FullViewportUpdate)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.rubberband = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)

        # Setup scene.
        scene = NodeScene(self)

        sceneWidth = config['scene_width']
        sceneHeight = config['scene_height']
        scene.setSceneRect(0, 0, sceneWidth, sceneHeight)
        self.setScene(scene)
        # Connect scene node moved signal
        scene.signal_NodeMoved.connect(self.signal_NodeMoved)

        # Tablet zoom.
        self.previousMouseOffset = 0
        self.zoomDirection = 0
        self.zoomIncr = 0

        # Connect signals.
        self.scene().selectionChanged.connect(self._returnSelection)


    # NODES
    def createNode(self, name='default', preset='node_default', position=None, alternate=True):
        """
        Create a new node with a given name, position and color.

        :type  name: str.
        :param name: The name of the node. The name has to be unique
                     as it is used as a key to store the node object.

        :type  preset: str.
        :param preset: The name of graphical preset in the config file.

        :type  position: QtCore.QPoint.
        :param position: The position of the node once created. If None,
                         it will be created at the center of the scene.

        :type  alternate: bool.
        :param alternate: The attribute color alternate state, if True,
                          every 2 attribute the color will be slightly
                          darker.

        :return : The created node

        """
        # Check for name clashes
        if name in self.scene().nodes.keys():
            print 'A node with the same name already exists : {0}'.format(name)
            print 'Node creation aborted !'
            return
        else:
            nodeItem = NodeItem(name=name, alternate=alternate, preset=preset,
                                config=self.config)

            # Store node in scene.
            self.scene().nodes[name] = nodeItem

            if not position:
                # Get the center of the view.
                p = self.viewport().rect().topLeft()
                p.setX(p.x() + 50)
                p.setY(p.y() + 50)
                position = self.mapToScene(p)

            # Set node position.
            self.scene().addItem(nodeItem)
            #nodeItem.setPos(position - nodeItem.nodeCenter)
            nodeItem.setPos(position)

            # Emit signal.
            self.signal_NodeCreated.emit(name)

            return nodeItem

    def deleteNode(self, node):
        """
        Delete the specified node from the view.

        :type  node: class.
        :param node: The node instance that you want to delete.

        """
        if not node in self.scene().nodes.values():
            print 'Node object does not exist !'
            print 'Node deletion aborted !'
            return

        if node in self.scene().nodes.values():
            nodeName = node.name
            node._remove()

            # Emit signal.
            self.signal_NodeDeleted.emit([nodeName])

    def editNode(self, node, newName=None):
        """
        Rename an existing node.

        :type  node: class.
        :param node: The node instance that you want to delete.

        :type  newName: str.
        :param newName: The new name for the given node.

        """
        if not node in self.scene().nodes.values():
            print 'Node object does not exist !'
            print 'Node edition aborted !'
            return

        oldName = node.name

        if newName != None:
            # Check for name clashes
            if newName in self.scene().nodes.keys():
                print 'A node with the same name already exists : {0}'.format(newName)
                print 'Node edition aborted !'
                return
            else:
                node.name = newName

        # Replace node data.
        self.scene().nodes[newName] = self.scene().nodes[oldName]
        self.scene().nodes.pop(oldName)

        # Store new node name in the connections
        if node.sockets:
            for socket in node.sockets.values():
                for connection in socket.connections:
                    connection.socketNode = newName

        if node.plugs:
            for plug in node.plugs.values():
                for connection in plug.connections:
                    connection.plugNode = newName

        node.update()

        # Emit signal.
        self.signal_NodeEdited.emit(oldName, newName)


    # ATTRS
    def createAttribute(self, node, name='default', index=-1, preset='attr_default', plug=True, socket=True, dataType=None):
        """
        Create a new attribute with a given name.

        :type  node: class.
        :param node: The node instance that you want to delete.

        :type  name: str.
        :param name: The name of the attribute. The name has to be
                     unique as it is used as a key to store the node
                     object.

        :type  index: int.
        :param index: The index of the attribute in the node.

        :type  preset: str.
        :param preset: The name of graphical preset in the config file.

        :type  plug: bool.
        :param plug: Whether or not this attribute can emit connections.

        :type  socket: bool.
        :param socket: Whether or not this attribute can receive
                       connections.

        :type  dataType: type.
        :param dataType: Type of the data represented by this attribute
                         in order to highlight attributes of the same
                         type while performing a connection.

        """
        if not node in self.scene().nodes.values():
            print 'Node object does not exist !'
            print 'Attribute creation aborted !'
            return

        if name in node.attrs:
            print 'An attribute with the same name already exists : {0}'.format(name)
            print 'Attribute creation aborted !'
            return

        node._createAttribute(name=name, index=index, preset=preset, plug=plug, socket=socket, dataType=dataType)

        # Emit signal.
        self.signal_AttrCreated.emit(node.name, index)

    def deleteAttribute(self, node, index):
        """
        Delete the specified attribute.

        :type  node: class.
        :param node: The node instance that you want to delete.

        :type  index: int.
        :param index: The index of the attribute in the node.

        """
        if not node in self.scene().nodes.values():
            print 'Node object does not exist !'
            print 'Attribute deletion aborted !'
            return

        node._deleteAttribute(index)

        # Emit signal.
        self.signal_AttrDeleted.emit(node.name, index)

    def editAttribute(self, node, index, newName=None, newIndex=None):
        """
        Edit the specified attribute.

        :type  node: class.
        :param node: The node instance that you want to delete.

        :type  index: int.
        :param index: The index of the attribute in the node.

        :type  newName: str.
        :param newName: The new name for the given attribute.

        :type  newIndex: int.
        :param newIndex: The index for the given attribute.

        """
        if not node in self.scene().nodes.values():
            print 'Node object does not exist !'
            print 'Attribute creation aborted !'
            return

        if newName != None:
            if newName in node.attrs:
                print 'An attribute with the same name already exists : {0}'.format(newName)
                print 'Attribute edition aborted !'
                return
            else:
                oldName = node.attrs[index]

            # Rename in the slot item(s).
            if node.attrsData[oldName]['plug']:
                node.plugs[oldName].attribute = newName
                node.plugs[newName] = node.plugs[oldName]
                node.plugs.pop(oldName)
                for connection in node.plugs[newName].connections:
                    connection.plugAttr = newName

            if node.attrsData[oldName]['socket']:
                node.sockets[oldName].attribute = newName
                node.sockets[newName] = node.sockets[oldName]
                node.sockets.pop(oldName)
                for connection in node.sockets[newName].connections:
                    connection.socketAttr = newName

            # Replace attribute data.
            node.attrsData[oldName]['name'] = newName
            node.attrsData[newName] = node.attrsData[oldName]
            node.attrsData.pop(oldName)
            node.attrs[index] = newName

        if isinstance(newIndex, int):
            attrName = node.attrs[index]

            swapListIndices(node.attrs, index, newIndex)

            # Refresh connections.
            for plug in node.plugs.values():
                plug.update()
                if plug.connections:
                    for connection in plug.connections:
                        if isinstance(connection.source, PlugItem):
                            connection.source = plug
                            connection.source_point = plug.center()
                        else:
                            connection.target = plug
                            connection.target_point = plug.center()
                        if newName:
                            connection.plugAttr = newName
                        connection.updatePath()

            for socket in node.sockets.values():
                socket.update()
                if socket.connections:
                    for connection in socket.connections:
                        if isinstance(connection.source, SocketItem):
                            connection.source = socket
                            connection.source_point = socket.center()
                        else:
                            connection.target = socket
                            connection.target_point = socket.center()
                        if newName:
                            connection.socketAttr = newName
                        connection.updatePath()

            self.scene().update()

        node.update()

        # Emit signal.
        if newIndex:
            self.signal_AttrEdited.emit(node.name, index, newIndex)
        else:
            self.signal_AttrEdited.emit(node.name, index, index)

    def createConnection(self, sourceNode, sourceAttr, targetNode, targetAttr):
        """
        Create a manual connection.

        :type  sourceNode: str.
        :param sourceNode: Node that emits the connection.

        :type  sourceAttr: str.
        :param sourceAttr: Attribute that emits the connection.

        :type  targetNode: str.
        :param targetNode: Node that receives the connection.

        :type  targetAttr: str.
        :param targetAttr: Attribute that receives the connection.

        """
        plug = self.scene().nodes[sourceNode].plugs[sourceAttr]
        socket = self.scene().nodes[targetNode].sockets[targetAttr]

        connection = ConnectionItem(plug.center(), socket.center(), plug, socket)

        connection.plugNode = plug.parentItem().name
        connection.plugAttr = plug.attribute
        connection.socketNode = socket.parentItem().name
        connection.socketAttr = socket.attribute

        plug.connect(socket, connection)
        socket.connect(plug, connection)

        connection.updatePath()

        self.scene().addItem(connection)

        return connection

    def evaluateGraph(self):
        """
        Create a list of connection tuples.
        [("sourceNode.attribute", "TargetNode.attribute"), ...]

        """
        scene = self.scene()

        data = list()

        for item in scene.items():
            if isinstance(item, ConnectionItem):
                connection = item

                data.append(connection._outputConnectionData())

        # Emit Signal
        self.signal_GraphEvaluated.emit()

        return data

    def clearGraph(self):
        """
        Clear the graph.

        """
        self.scene().clear()
        self.scene().nodes = dict()

        # Emit signal.
        self.signal_GraphCleared.emit()

    ##################################################################
    # END API
    ##################################################################


class NodeScene(QtWidgets.QGraphicsScene):

    """
    The scene displaying all the nodes.

    """
    signal_NodeMoved = QtCore.pyqtSignal(str, object)

    def __init__(self, parent):
        """
        Initialize the class.

        """
        super(NodeScene, self).__init__(parent)

        # General.
        self.gridSize = parent.config['grid_size']

        # Nodes storage.
        self.nodes = dict()

    def dragEnterEvent(self, event):
        """
        Make the dragging of nodes into the scene possible.

        """
        event.setDropAction(QtCore.Qt.MoveAction)
        event.accept()

    def dragMoveEvent(self, event):
        """
        Make the dragging of nodes into the scene possible.

        """
        event.setDropAction(QtCore.Qt.MoveAction)
        event.accept()

    def dropEvent(self, event):
        """
        Create a node from the dropped item.

        """
        # Emit signal.
        self.signal_Dropped.emit(event.scenePos())

        event.accept()

    def drawBackground(self, painter, rect):
        """
        Draw a grid in the background.

        """
        if self.views()[0].gridVisToggle:
            leftLine = rect.left() - rect.left() % self.gridSize
            topLine = rect.top() - rect.top() % self.gridSize
            lines = list()

            i = int(leftLine)
            while i < int(rect.right()):
                lines.append(QtCore.QLineF(i, rect.top(), i, rect.bottom()))
                i += self.gridSize

            u = int(topLine)
            while u < int(rect.bottom()):
                lines.append(QtCore.QLineF(rect.left(), u, rect.right(), u))
                u += self.gridSize

            self.pen = QtGui.QPen()
            config = self.parent().config
            self.pen.setColor(convertDataToColor(config['grid_color']))
            self.pen.setWidth(0)
            painter.setPen(self.pen)
            painter.drawLines(lines)

    def updateScene(self):
        """
        Update the connections position.

        """
        for connection in [i for i in self.items() if isinstance(i, ConnectionItem)]:
            connection.target_point = connection.target.center()
            connection.source_point = connection.source.center()
            connection.updatePath()


class NodeItem(QtWidgets.QGraphicsItem):

    """
    A graphic representation of a node containing attributes.

    """

    def __init__(self, name, alternate, preset, config):
        """
        Initialize the class.

        :type  name: str.
        :param name: The name of the node. The name has to be unique
                     as it is used as a key to store the node object.

        :type  alternate: bool.
        :param alternate: The attribute color alternate state, if True,
                          every 2 attribute the color will be slightly
                          darker.

        :type  preset: str.
        :param preset: The name of graphical preset in the config file.

        """
        super(NodeItem, self).__init__()

        self.setZValue(1)

        # Storage
        self.name = name
        self.alternate = alternate
        self.nodePreset = preset
        self.attrPreset = None

        # Attributes storage.
        self.attrs = list()
        self.attrsData = dict()
        self.attrCount = 0
        self.currentDataType = None

        self.plugs = dict()
        self.sockets = dict()

        # Methods.
        self._createStyle(config)

    @property
    def height(self):
        """
        Increment the final height of the node every time an attribute
        is created.

        """
        if self.attrCount > 0:
            return (self.baseHeight +
                    self.attrHeight * self.attrCount +
                    self.border +
                    0.5 * self.radius)
        else:
            return self.baseHeight

    @property
    def width(self):
        """
        Calculate width dynamically.
        :return:
        """

        w = self.baseWidth #min width
        for attr in self.attrs:
            w = max(w,self._attrFontMetrics.width(attr)+self.radius*2+self.border)
        return w

    @property
    def pen(self):
        """
        Return the pen based on the selection state of the node.

        """
        if self.isSelected():
            return self._penSel
        else:
            return self._pen

    def _createStyle(self, config):
        """
        Read the node style from the configuration file.

        """
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable)

        # Dimensions.
        self.baseWidth  = config['node_width']
        self.baseHeight = config['node_height']
        self.attrHeight = config['node_attr_height']
        self.border = config['node_border']
        self.radius = config['node_radius']

        self.nodeCenter = QtCore.QPointF()
        self.nodeCenter.setX(self.width / 2.0)
        self.nodeCenter.setY(self.height / 2.0)

        self._brush = QtGui.QBrush()
        self._brush.setStyle(QtCore.Qt.SolidPattern)
        self._brush.setColor(convertDataToColor(config[self.nodePreset]['bg']))

        self._pen = QtGui.QPen()
        self._pen.setStyle(QtCore.Qt.SolidLine)
        self._pen.setWidth(self.border)
        self._pen.setColor(convertDataToColor(config[self.nodePreset]['border']))

        self._penSel = QtGui.QPen()
        self._penSel.setStyle(QtCore.Qt.SolidLine)
        self._penSel.setWidth(self.border)
        self._penSel.setColor(convertDataToColor(config[self.nodePreset]['border_sel']))

        self._textPen = QtGui.QPen()
        self._textPen.setStyle(QtCore.Qt.SolidLine)
        self._textPen.setColor(convertDataToColor(config[self.nodePreset]['text']))

        self._nodeTextFont = QtGui.QFont(config['node_font'], config['node_font_size'], QtGui.QFont.Bold)
        self._attrTextFont = QtGui.QFont(config['attr_font'], config['attr_font_size'], QtGui.QFont.Normal)
        self._attrFontMetrics = QtGui.QFontMetrics(self._attrTextFont)

        self._attrBrush = QtGui.QBrush()
        self._attrBrush.setStyle(QtCore.Qt.SolidPattern)

        self._attrBrushAlt = QtGui.QBrush()
        self._attrBrushAlt.setStyle(QtCore.Qt.SolidPattern)

        self._attrPen = QtGui.QPen()
        self._attrPen.setStyle(QtCore.Qt.SolidLine)

    def _createAttribute(self, name, index, preset, plug, socket, dataType):
        """
        Create an attribute by expanding the node, adding a label and
        connection items.

        :type  name: str.
        :param name: The name of the attribute. The name has to be
                     unique as it is used as a key to store the node
                     object.

        :type  index: int.
        :param index: The index of the attribute in the node.

        :type  preset: str.
        :param preset: The name of graphical preset in the config file.

        :type  plug: bool.
        :param plug: Whether or not this attribute can emit connections.

        :type  socket: bool.
        :param socket: Whether or not this attribute can receive
                       connections.

        :type  dataType: type.
        :param dataType: Type of the data represented by this attribute
                         in order to highlight attributes of the same
                         type while performing a connection.

        """
        if name in self.attrs:
            print 'An attribute with the same name already exists on this node : {0}'.format(name)
            print 'Attribute creation aborted !'
            return

        self.attrPreset = preset

        # Create a plug connection item.
        if plug:
            plugInst = PlugItem(parent=self,
                                attribute=name,
                                index=self.attrCount,
                                preset=preset,
                                dataType=dataType)
            self.plugs[name] = plugInst

        # Create a socket connection item.
        if socket:
            socketInst = SocketItem(parent=self,
                                    attribute=name,
                                    index=self.attrCount,
                                    preset=preset,
                                    dataType=dataType)

            self.sockets[name] = socketInst

        self.attrCount += 1

        # Add the attribute based on its index.
        if index == -1 or index > self.attrCount:
            self.attrs.append(name)
        else:
            self.attrs.insert(index, name)

        # Store attr data.
        self.attrsData[name] = {'name': name,
                                'socket': socket,
                                'plug': plug,
                                'preset': preset,
                                'dataType': dataType}

        # Update node height.
        self.update()

    def _deleteAttribute(self, index):
        """
        Remove an attribute by reducing the node, removing the label
        and the connection items.

        :type  index: int.
        :param index: The index of the attribute in the node.

        """
        name = self.attrs[index]

        # Remove socket and its connections.
        if name in self.sockets.keys():
            for connection in self.sockets[name].connections:
                connection._remove()

            self.scene().removeItem(self.sockets[name])
            self.sockets.pop(name)

        # Remove plug and its connections.
        if name in self.plugs.keys():
            for connection in self.plugs[name].connections:
                connection._remove()

            self.scene().removeItem(self.plugs[name])
            self.plugs.pop(name)

        # Reduce node height.
        if self.attrCount > 0:
            self.attrCount -= 1

        # Remove attribute from node.
        if name in self.attrs:
            self.attrs.remove(name)

        self.update()

    def _remove(self):
        """
        Remove this node instance from the scene.

        Make sure that all the connections to this node are also removed
        in the process

        """
        self.scene().nodes.pop(self.name)

        # Remove all sockets connections.
        for socket in self.sockets.values():
            while len(socket.connections)>0:
                socket.connections[0]._remove()

        # Remove all plugs connections.
        for plug in self.plugs.values():
            while len(plug.connections)>0:
                plug.connections[0]._remove()

        # Remove node.
        scene = self.scene()
        scene.removeItem(self)
        scene.update()

    def boundingRect(self):
        """
        The bounding rect based on the width and height variables.

        """
        rect = QtCore.QRect(0, 0, self.width, self.height)
        rect = QtCore.QRectF(rect)
        return rect

    def shape(self):
        """
        The shape of the item.

        """
        path = QtGui.QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint(self, painter, option, widget):
        """
        Paint the node and attributes.

        """
        # Node base.
        painter.setBrush(self._brush)
        painter.setPen(self.pen)

        painter.drawRoundedRect(0, 0,
                                self.width,
                                self.height,
                                self.radius,
                                self.radius)

        # Node label.
        painter.setPen(self._textPen)
        painter.setFont(self._nodeTextFont)

        metrics = QtGui.QFontMetrics(painter.font())
        text_width = metrics.boundingRect(self.name).width() + 14
        text_height = metrics.boundingRect(self.name).height() + 14
        margin = (text_width - self.baseWidth) * 0.5
        textRect = QtCore.QRect(-margin,
                                -text_height,
                                text_width,
                                text_height)

        painter.drawText(textRect,
                         QtCore.Qt.AlignCenter,
                         self.name)


        # Attributes.
        offset = 0
        for attr in self.attrs:
            nodzInst = self.scene().views()[0]
            config = nodzInst.config

            # Attribute rect.
            rect = QtCore.QRect(self.border / 2,
                                self.baseHeight - self.radius + offset,
                                self.width - self.border,
                                self.attrHeight)



            attrData = self.attrsData[attr]
            name = attr

            preset = attrData['preset']


            # Attribute base.
            self._attrBrush.setColor(convertDataToColor(config[preset]['bg']))
            if self.alternate:
                self._attrBrushAlt.setColor(convertDataToColor(config[preset]['bg'], True, config['alternate_value']))

            self._attrPen.setColor(convertDataToColor([0, 0, 0, 0]))
            painter.setPen(self._attrPen)
            painter.setBrush(self._attrBrush)
            if (offset / self.attrHeight) % 2:
                painter.setBrush(self._attrBrushAlt)

            painter.drawRect(rect)

            # Attribute label.
            painter.setPen(convertDataToColor(config[preset]['text']))
            painter.setFont(self._attrTextFont)

            # Search non-connectable attributes.
            if nodzInst.drawingConnection:
                if self == nodzInst.currentHoveredNode:
                    if (attrData['dataType'] != nodzInst.sourceSlot.dataType or
                        (nodzInst.sourceSlot.slotType == 'plug' and attrData['socket'] == False or
                         nodzInst.sourceSlot.slotType == 'socket' and attrData['plug'] == False)):
                        # Set non-connectable attributes color.
                        painter.setPen(convertDataToColor(config['non_connectable_color']))

            textRect = QtCore.QRect(rect.left() + self.radius,
                                     rect.top(),
                                     rect.width() - 2*self.radius,
                                     rect.height())
            painter.drawText(textRect, QtCore.Qt.AlignVCenter, name)

            offset += self.attrHeight

    def mousePressEvent(self, event):
        """
        Keep the selected node on top of the others.

        """
        nodes = self.scene().nodes
        for node in nodes.values():
            node.setZValue(1)

        for item in self.scene().items():
            if isinstance(item, ConnectionItem):
                item.setZValue(1)

        self.setZValue(2)

        super(NodeItem, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """
        .

        """
        if self.scene().views()[0].gridVisToggle:
            if self.scene().views()[0].gridSnapToggle or self.scene().views()[0]._nodeSnap:
                gridSize = self.scene().gridSize

                currentPos = self.mapToScene(event.pos().x() - self.width / 2,
                                             event.pos().y() - self.height / 2)

                snap_x = (round(currentPos.x() / gridSize) * gridSize) - gridSize/4
                snap_y = (round(currentPos.y() / gridSize) * gridSize) - gridSize/4
                snap_pos = QtCore.QPointF(snap_x, snap_y)
                self.setPos(snap_pos)

                self.scene().updateScene()
            else:
                self.scene().updateScene()
                super(NodeItem, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """
        .

        """
        # Emit node moved signal.
        self.scene().signal_NodeMoved.emit(self.name, self.pos())
        super(NodeItem, self).mouseReleaseEvent(event)

    def hoverLeaveEvent(self, event):
        """
        .

        """
        nodzInst = self.scene().views()[0]

        for item in nodzInst.scene().items():
            if isinstance(item, ConnectionItem):
                item.setZValue(0)

        super(NodeItem, self).hoverLeaveEvent(event)


class SlotItem(QtWidgets.QGraphicsItem):

    """
    The base class for graphics item representing attributes hook.

    """

    def __init__(self, parent, attribute, preset, index, dataType):
        """
        Initialize the class.

        :param parent: The parent item of the slot.
        :type  parent: QtWidgets.QGraphicsItem instance.

        :param attribute: The attribute associated to the slot.
        :type  attribute: String.

        :param index: int.
        :type  index: The index of the attribute in the node.

        :type  preset: str.
        :param preset: The name of graphical preset in the config file.

        :param dataType: The data type associated to the attribute.
        :type  dataType: Type.

        """
        super(SlotItem, self).__init__(parent)

        # Status.
        self.setAcceptHoverEvents(True)

        # Storage.
        self.slotType = None
        self.attribute = attribute
        self.preset = preset
        self.index = index
        self.dataType = dataType

        # Style.
        self.brush = QtGui.QBrush()
        self.brush.setStyle(QtCore.Qt.SolidPattern)

        self.pen = QtGui.QPen()
        self.pen.setStyle(QtCore.Qt.SolidLine)

        # Connections storage.
        self.connected_slots = list()
        self.newConnection = None
        self.connections = list()

    def mousePressEvent(self, event):
        """
        Start the connection process.

        """
        if event.button() == QtCore.Qt.LeftButton:
            self.newConnection = ConnectionItem(self.center(),
                                                self.mapToScene(event.pos()),
                                                self,
                                                None)

            self.connections.append(self.newConnection)
            self.scene().addItem(self.newConnection)

            nodzInst = self.scene().views()[0]
            nodzInst.drawingConnection = True
            nodzInst.sourceSlot = self
            nodzInst.currentDataType = self.dataType
        else:
            super(SlotItem, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """
        Update the new connection's end point position.

        """
        nodzInst = self.scene().views()[0]
        config = nodzInst.config
        if nodzInst.drawingConnection:
            mbb = createPointerBoundingBox(pointerPos=event.scenePos().toPoint(),
                                                  bbSize=config['mouse_bounding_box'])

            # Get nodes in pointer's bounding box.
            targets = self.scene().items(mbb)

            if any(isinstance(target, NodeItem) for target in targets):
                if self.parentItem() not in targets:
                    for target in targets:
                        if isinstance(target, NodeItem):
                            nodzInst.currentHoveredNode = target
            else:
                nodzInst.currentHoveredNode = None

            # Set connection's end point.
            self.newConnection.target_point = self.mapToScene(event.pos())
            self.newConnection.updatePath()
        else:
            super(SlotItem, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """
        Apply the connection if target_slot is valid.

        """
        nodzInst = self.scene().views()[0]
        if event.button() == QtCore.Qt.LeftButton:
            nodzInst.drawingConnection = False
            nodzInst.currentDataType = None

            target = self.scene().itemAt(event.scenePos().toPoint(), QtGui.QTransform())

            if not isinstance(target, SlotItem):
                self.newConnection._remove()
                super(SlotItem, self).mouseReleaseEvent(event)
                return

            if target.accepts(self):
                self.newConnection.target = target
                self.newConnection.source = self
                self.newConnection.target_point = target.center()
                self.newConnection.source_point = self.center()

                # Perform the ConnectionItem.
                self.connect(target, self.newConnection)
                target.connect(self, self.newConnection)

                self.newConnection.updatePath()
            else:
                self.newConnection._remove()
        else:
            super(SlotItem, self).mouseReleaseEvent(event)

        nodzInst.currentHoveredNode = None

    def shape(self):
        """
        The shape of the Slot is a circle.

        """
        path = QtGui.QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint(self, painter, option, widget):
        """
        Paint the Slot.

        """
        painter.setBrush(self.brush)
        painter.setPen(self.pen)

        nodzInst = self.scene().views()[0]
        config = nodzInst.config
        if nodzInst.drawingConnection:
            if self.parentItem() == nodzInst.currentHoveredNode:
                painter.setBrush(convertDataToColor(config['non_connectable_color']))
                if (self.slotType == nodzInst.sourceSlot.slotType or (self.slotType != nodzInst.sourceSlot.slotType and self.dataType != nodzInst.sourceSlot.dataType)):
                    painter.setBrush(convertDataToColor(config['non_connectable_color']))
                else:
                    _penValid = QtGui.QPen()
                    _penValid.setStyle(QtCore.Qt.SolidLine)
                    _penValid.setWidth(2)
                    _penValid.setColor(QtGui.QColor(255, 255, 255, 255))
                    painter.setPen(_penValid)
                    painter.setBrush(self.brush)

        painter.drawEllipse(self.boundingRect())

    def center(self):
        """
        Return The center of the Slot.

        """
        rect = self.boundingRect()
        center = QtCore.QPointF(rect.x() + rect.width() * 0.5,
                                rect.y() + rect.height() * 0.5)

        return self.mapToScene(center)


class PlugItem(SlotItem):

    """
    A graphics item representing an attribute out hook.

    """

    def __init__(self, parent, attribute, index, preset, dataType):
        """
        Initialize the class.

        :param parent: The parent item of the slot.
        :type  parent: QtWidgets.QGraphicsItem instance.

        :param attribute: The attribute associated to the slot.
        :type  attribute: String.

        :param index: int.
        :type  index: The index of the attribute in the node.

        :type  preset: str.
        :param preset: The name of graphical preset in the config file.

        :param dataType: The data type associated to the attribute.
        :type  dataType: Type.

        """
        super(PlugItem, self).__init__(parent, attribute, preset, index, dataType)
        # Storage.
        self.attributte = attribute
        self.preset = preset
        self.slotType = 'plug'

        # Methods.
        self._createStyle(parent)

    def _createStyle(self, parent):
        """
        Read the attribute style from the configuration file.

        """
        config = parent.scene().views()[0].config
        self.brush = QtGui.QBrush()
        self.brush.setStyle(QtCore.Qt.SolidPattern)
        self.brush.setColor(convertDataToColor(config[self.preset]['plug']))

    def boundingRect(self):
        """
        The bounding rect based on the width and height variables.

        """
        width = height = self.parentItem().attrHeight / 4.0

        nodzInst = self.scene().views()[0]
        config = nodzInst.config

        x = self.parentItem().width - (width / 2.0)
        y = (self.parentItem().baseHeight - config['node_radius'] +
             self.parentItem().attrHeight * (3.0/8.0) +
             self.parentItem().attrs.index(self.attribute) * self.parentItem().attrHeight)

        rect = QtCore.QRectF(QtCore.QRect(x, y, width, height))
        return rect

    def accepts(self, socket_item):
        """
        Only accepts socket items that belong to other nodes.

        """
        if isinstance(socket_item, SocketItem):
            if self.parentItem() != socket_item.parentItem():
                if socket_item.dataType == self.dataType:
                    if socket_item in self.connected_slots:
                        return False
                    else:
                        return True
            else:
                return False
        else:
            return False

    def connect(self, socket_item, connection):
        """
        Connect to the given socket_item.

        """
        # Populate connection.
        connection.socketItem = socket_item
        connection.plugNode = self.parentItem().name
        connection.plugAttr = self.attribute

        # Add socket to connected slots.
        if socket_item in self.connected_slots:
            self.connected_slots.remove(socket_item)
        self.connected_slots.append(socket_item)

        # Add connection.
        if connection not in self.connections:
            self.connections.append(connection)

        # Emit signal.
        nodzInst = self.scene().views()[0]
        nodzInst.signal_PlugConnected.emit(connection.plugNode, connection.plugAttr, connection.socketNode, connection.socketAttr)

    def disconnect(self, connection):
        """
        Disconnect the given connection from this plug item.

        """
        # Emit signal.
        nodzInst = self.scene().views()[0]
        nodzInst.signal_PlugDisconnected.emit(connection.plugNode, connection.plugAttr, connection.socketNode, connection.socketAttr)

        # Remove connected socket from plug
        if connection.socketItem in self.connected_slots:
            self.connected_slots.remove(connection.socketItem)
        # Remove connection
        self.connections.remove(connection)


class SocketItem(SlotItem):

    """
    A graphics item representing an attribute in hook.

    """

    def __init__(self, parent, attribute, index, preset, dataType):
        """
        Initialize the socket.

        :param parent: The parent item of the slot.
        :type  parent: QtWidgets.QGraphicsItem instance.

        :param attribute: The attribute associated to the slot.
        :type  attribute: String.

        :param index: int.
        :type  index: The index of the attribute in the node.

        :type  preset: str.
        :param preset: The name of graphical preset in the config file.

        :param dataType: The data type associated to the attribute.
        :type  dataType: Type.

        """
        super(SocketItem, self).__init__(parent, attribute, preset, index, dataType)
        # Storage.

        self.attributte = attribute
        self.preset = preset
        self.slotType = 'socket'

        # Methods.
        self._createStyle(parent)

    def _createStyle(self, parent):
        """
        Read the attribute style from the configuration file.

        """
        config = parent.scene().views()[0].config
        self.brush = QtGui.QBrush()
        self.brush.setStyle(QtCore.Qt.SolidPattern)
        self.brush.setColor(convertDataToColor(config[self.preset]['socket']))

    def boundingRect(self):
        """
        The bounding rect based on the width and height variables.

        """
        width = height = self.parentItem().attrHeight / 4.0

        nodzInst = self.scene().views()[0]
        config = nodzInst.config

        x = - width / 2.0
        y = (self.parentItem().baseHeight - config['node_radius'] +
             self.parentItem().attrHeight * (3.0 / 8.0) +
             self.parentItem().attrs.index(self.attribute) * self.parentItem().attrHeight )

        rect = QtCore.QRectF(QtCore.QRect(x, y, width, height))
        return rect

    def accepts(self, plug_item):
        """
        Only accepts plug items that belong to other nodes.

        """
        if isinstance(plug_item, PlugItem):
            if (self.parentItem() != plug_item.parentItem() and
                len(self.connected_slots) <= 1):
                if plug_item.dataType == self.dataType:
                    if plug_item in self.connected_slots:
                        return False
                    else:
                        return True
            else:
                return False
        else:
            return False

    def connect(self, plug_item, connection):
        """
        Connect to the given plug item.

        """
        if len(self.connected_slots) > 0:
            # Already connected.
            self.connections[0]._remove()
            self.connected_slots = list()

        # Populate connection.
        connection.plugItem = plug_item
        connection.socketNode = self.parentItem().name
        connection.socketAttr = self.attribute

        # Add plug to connected slots.
        self.connected_slots.append(plug_item)

        # Add connection.
        if connection not in self.connections:
            self.connections.append(connection)

        # Emit signal.
        nodzInst = self.scene().views()[0]
        nodzInst.signal_SocketConnected.emit(connection.plugNode, connection.plugAttr, connection.socketNode, connection.socketAttr)

    def disconnect(self, connection):
        """
        Disconnect the given connection from this socket item.

        """
        # Emit signal.
        nodzInst = self.scene().views()[0]
        nodzInst.signal_SocketDisconnected.emit(connection.plugNode, connection.plugAttr, connection.socketNode, connection.socketAttr)

        # Remove connected plugs
        if connection.plugItem in self.connected_slots:
            self.connected_slots.remove(connection.plugItem)
        # Remove connections
        self.connections.remove(connection)


class ConnectionItem(QtWidgets.QGraphicsPathItem):

    """
    A graphics path representing a connection between two attributes.

    """

    def __init__(self, source_point, target_point, source, target):
        """
        Initialize the class.

        :param sourcePoint: Source position of the connection.
        :type  sourcePoint: QPoint.

        :param targetPoint: Target position of the connection
        :type  targetPoint: QPoint.

        :param source: Source item (plug or socket).
        :type  source: class.

        :param target: Target item (plug or socket).
        :type  target: class.

        """
        super(ConnectionItem, self).__init__()

        self.setZValue(1)

        # Storage.
        self.socketNode = None
        self.socketAttr = None
        self.plugNode = None
        self.plugAttr = None

        self.source_point = source_point
        self.target_point = target_point
        self.source = source
        self.target = target

        self.plugItem = None
        self.socketItem = None

        self.movable_point = None

        self.data = tuple()

        # Methods.
        self._createStyle()

    def _createStyle(self):
        """
        Read the connection style from the configuration file.

        """
        config = self.source.scene().views()[0].config
        self.setAcceptHoverEvents(True)
        self.setZValue(-1)

        self._pen = QtGui.QPen(convertDataToColor(config['connection_color']))
        self._pen.setWidth(config['connection_width'])

    def _outputConnectionData(self):
        """
        .

        """
        return ("{0}.{1}".format(self.plugNode, self.plugAttr),
                "{0}.{1}".format(self.socketNode, self.socketAttr))

    def mousePressEvent(self, event):
        """
        Snap the Connection to the mouse.

        """
        nodzInst = self.scene().views()[0]

        for item in nodzInst.scene().items():
            if isinstance(item, ConnectionItem):
                item.setZValue(0)

        nodzInst.drawingConnection = True

        d_to_target = (event.pos() - self.target_point).manhattanLength()
        d_to_source = (event.pos() - self.source_point).manhattanLength()
        if d_to_target < d_to_source:
            self.target_point = event.pos()
            self.movable_point = 'target_point'
            self.target.disconnect(self)
            self.target = None
            nodzInst.sourceSlot = self.source
        else:
            self.source_point = event.pos()
            self.movable_point = 'source_point'
            self.source.disconnect(self)
            self.source = None
            nodzInst.sourceSlot = self.target

        self.updatePath()

    def mouseMoveEvent(self, event):
        """
        Move the Connection with the mouse.

        """
        nodzInst = self.scene().views()[0]
        config = nodzInst.config

        mbb = createPointerBoundingBox(pointerPos=event.scenePos().toPoint(),
                                              bbSize=config['mouse_bounding_box'])

        # Get nodes in pointer's bounding box.
        targets = self.scene().items(mbb)

        if any(isinstance(target, NodeItem) for target in targets):

            if nodzInst.sourceSlot.parentItem() not in targets:
                for target in targets:
                    if isinstance(target, NodeItem):
                        nodzInst.currentHoveredNode = target
        else:
            nodzInst.currentHoveredNode = None

        if self.movable_point == 'target_point':
            self.target_point = event.pos()
        else:
            self.source_point = event.pos()

        self.updatePath()

    def mouseReleaseEvent(self, event):
        """
        Create a Connection if possible, otherwise delete it.

        """
        nodzInst = self.scene().views()[0]
        nodzInst.drawingConnection = False

        slot = self.scene().itemAt(event.scenePos().toPoint(), QtGui.QTransform())

        if not isinstance(slot, SlotItem):
            self._remove()
            self.updatePath()
            super(ConnectionItem, self).mouseReleaseEvent(event)
            return

        if self.movable_point == 'target_point':
            if slot.accepts(self.source):
                # Plug reconnection.
                self.target = slot
                self.target_point = slot.center()
                plug = self.source
                socket = self.target

                # Reconnect.
                socket.connect(plug, self)

                self.updatePath()
            else:
                self._remove()

        else:
            if slot.accepts(self.target):
                # Socket Reconnection
                self.source = slot
                self.source_point = slot.center()
                socket = self.target
                plug = self.source

                # Reconnect.
                plug.connect(socket, self)

                self.updatePath()
            else:
                self._remove()

    def _remove(self):
        """
        Remove this Connection from the scene.

        """
        if self.source is not None:
            self.source.disconnect(self)
        if self.target is not None:
            self.target.disconnect(self)

        scene = self.scene()
        scene.removeItem(self)
        scene.update()

    def updatePath(self):
        """
        Update the path.

        """
        self.setPen(self._pen)

        path = QtGui.QPainterPath()
        path.moveTo(self.source_point)
        dx = (self.target_point.x() - self.source_point.x()) * 0.5
        dy = self.target_point.y() - self.source_point.y()
        ctrl1 = QtCore.QPointF(self.source_point.x() + dx, self.source_point.y() + dy * 0)
        ctrl2 = QtCore.QPointF(self.source_point.x() + dx, self.source_point.y() + dy * 1)
        path.cubicTo(ctrl1, ctrl2, self.target_point)

        self.setPath(path)

############################################################################################################################
############################################################################################################################
############################################################################################################################


######################################################################
# Test signals
######################################################################

# Nodes
@QtCore.pyqtSlot(str)
def on_nodeCreated(nodeName):
    print 'node created : ', nodeName

@QtCore.pyqtSlot(str)
def on_nodeDeleted(nodeName):
    print 'node deleted : ', nodeName

@QtCore.pyqtSlot(str, str)
def on_nodeEdited(nodeName, newName):
    print 'node edited : {0}, new name : {1}'.format(nodeName, newName)

@QtCore.pyqtSlot(str)
def on_nodeSelected(nodesName):
    print 'node selected : ', nodesName

@QtCore.pyqtSlot(str, object)
def on_nodeMoved(nodeName, nodePos):
    print 'node {0} moved to {1}'.format(nodeName, nodePos)

# Attrs
@QtCore.pyqtSlot(str, int)
def on_attrCreated(nodeName, attrId):
    print 'attr created : {0} at index : {1}'.format(nodeName, attrId)

@QtCore.pyqtSlot(str, int)
def on_attrDeleted(nodeName, attrId):
    print 'attr Deleted : {0} at old index : {1}'.format(nodeName, attrId)

@QtCore.pyqtSlot(str, int, int)
def on_attrEdited(nodeName, oldId, newId):
    print 'attr Edited : {0} at old index : {1}, new index : {2}'.format(nodeName, oldId, newId)

# Connections
@QtCore.pyqtSlot(str, str, str, str)
def on_connected(srcNodeName, srcPlugName, destNodeName, dstSocketName):
    print 'connected src: "{0}" at "{1}" to dst: "{2}" at "{3}"'.format(srcNodeName, srcPlugName, destNodeName, dstSocketName)

@QtCore.pyqtSlot(str, str, str, str)
def on_disconnected(srcNodeName, srcPlugName, destNodeName, dstSocketName):
    print 'disconnected src: "{0}" at "{1}" from dst: "{2}" at "{3}"'.format(srcNodeName, srcPlugName, destNodeName, dstSocketName)

# Graph
@QtCore.pyqtSlot()
def on_graphSaved():
    print 'graph saved !'

@QtCore.pyqtSlot()
def on_graphLoaded():
    print 'graph loaded !'

@QtCore.pyqtSlot()
def on_graphCleared():
    print 'graph cleared !'

@QtCore.pyqtSlot()
def on_graphEvaluated():
    print 'graph evaluated !'

# Other
@QtCore.pyqtSlot(object)
def on_keyPressed(key):
    print 'key pressed : ', key


def u(value, size):
    global endian
    if endian == 'big':
        e = ">"
    else:
        e = "<"
    if size == 2:
        return struct.unpack(e+"H", value)[0]
    elif size == 4:
        return struct.unpack(e+"I", value)[0]
    elif size == 8:
        return struct.unpack(e+"Q", value)[0]


class NotDefinedObjectException(Exception):
    def __init__(self, msg):
        super(NotDefinedObjectException, self).__init__(msg)

class NoMemberFoundException(Exception):
    def __init__(self, msg):
        super(NoMemberFoundException, self).__init__(msg)

class CMember(object):
    global bits, pat, nodz

    def __init__(self, address, offset, name, size, flag, member_id, idx, cobject=None):
        self.address = address
        self.offset = offset
        self.name = name
        self.size = size
        self.flag = flag
        self.member_id = member_id
        self.type = idc.get_type(self.member_id)
        self.is_array = False
        self.idx = idx
        self.cobject = cobject
        self.connected_cobject = None
        # even if use_dbg=False, get_bytes read memory from debugger. TODO check if this is true.
        if self.type is None:
            # Didn't defined type explicitly.

            # Default value is integer(size=1,2,4,8).
            if (idc.is_byte(self.flag) and self.size == 1) or (idc.is_word(self.flag) and self.size == 2) or (idc.is_dword(self.flag) and self.size == 4) or (idc.is_qword(self.flag) and self.size == 8):
                self.value = u(idc.get_bytes(address, size, False), size)
            else:
                # maybe list
                # TODO handle correctly if type isn't array (enum, bitfield, ...)
                if idc.is_enum0(self.flag) or idc.is_bf(self.flag):
                    raise Exception("Not implemented")
                self.is_array = True
                self.value = idc.get_bytes(address, size, False)
        else:
            self.type = re.sub(pat, '', self.type)
            # Struct or type defined explicitly.
            if self.is_ptr:
                self.value = u(idc.get_bytes(address, size, False), size)
            else:
                # handle type.
                self.value = idc.get_bytes(address, size, False)
        # TODO
        # if self.is_ptr() -> Find CMember to which it points.(via CObjectManager?)

    def connect(self, target_cmember):
        self.connected_cobject = target_cmember
        nodz.createConnection(str(self.cobject), str(self), str(target_cmember.cobject), str(target_cmember))

    @property
    def is_ptr(self):
        return idc.is_off0(self.flag)

    @property
    def is_valid_ptr(self):
        """

        :return:
        """
        global bits
        return self.is_ptr and idc.is_mapped(self.value)

    @property
    def ptr_struct_name(self):
        """
        Handy dereference structure name.
        struc_x *** -> struc_x **
        :return: structure name to which CMember point.
        """
        assert self.is_ptr
        if self.type is None:
            return None
        assert self.type[-1] == '*'
        return self.type[:-1].rstrip(' ')

    @property
    def is_struct(self):
        return idc.is_struct(self.flag)

    @property
    def bottom_y(self):
        """

        :return: max(self.bottom, max(self.childlen's bottom))
        """
        if self.idx == 0:
            return self.cobject.node.pos().y()

    def __repr__(self):
        # Do you want type name?
        # TODO if string, preview string?
        if isinstance(self.value, (int, long)):
            return self.name + '  ' + ("0x{0:0" + str(self.size * 2) + "x}").format(self.value)
        else:
            return self.name + '  ' + "PREVIEW"


class CObject(object):
    global nodz

    def __init__(self, address, struct_name, pos, cmanager=None, parent_cmember=None):
        self.address = address
        self.members = []
        self.struct_name = re.sub(pat, '', struct_name)
        self.struct_id = idaapi.get_struc_id(self.struct_name)
        self.size = idc.get_struc_size(self.struct_id)
        self.cmanager = cmanager
        # set parent object
        self.parent_cmember = parent_cmember
        self.node = nodz.createNode(name=str(self), preset='node_preset_1', position=pos)
        if self.struct_id == idc.BADADDR:
            raise NotDefinedObjectException(self.struct_name + ' isn\'t defined. Please insert into structure window.')
        if idc.is_union(self.struct_id):
            raise NotDefinedObjectException("Union Not supported now.")

        idx = 0 # TODO remove this and bottom_y of CMember
        for member in idautils.StructMembers(self.struct_id):
            offset, name, size = member
            # TODO if member is struct, expand struct members.
            # TODO if member is array, expand array members.( But db array is maybe string, and user don't want it to expand... ) Only expand dd|dw|dq array?
            cmember = CMember(address + offset, offset, name, size, idc.get_member_flag(self.struct_id, offset), idc.get_member_id(self.struct_id, offset), idx, cobject=self)
            self.members.append(cmember)
            idx += 1
        if self.members is []:
            raise NoMemberFoundException("No member found at " + struct_name)

        for member in self.members:
            nodz.createAttribute(node=self.node, name=str(member), index=-1, preset='attr_preset_1', plug=True, socket=True, dataType=str)

        pos = self.node.pos()
        pos.setX(self.right_end + 40) # shift right a little bit
        for member in self.members:
            if member.is_valid_ptr:
                if self.cmanager.is_contain(member.value):
                    # address already exists.
                    member.connect(self.cmanager.search_cmember(member.value))
                else:
                    # create cobject
                    cobj = self.cmanager.add_cobject(member.value, member.ptr_struct_name, pos, parent_cmember=member)
                    member.connect(cobj.members[0]) # connect to top member
                    pos.setY(cobj.bottom_y + 40) # shift down a little bit

    def is_contain(self, address):
        if self.address <= address < self.address + self.size:
            return True
        return False

    def search_cmember(self, address):
        for member in self.members:
            if member.address == address:
                return member
        return None

    @property
    def right_end(self):
        """

        :return:
        """
        return self.node.pos().x() + self.node.width

    @property
    def bottom_y(self):
        """

        :return: max(self.bottom, max(self.childlen's bottom))
        """
        bottom = self.node.pos().y() + self.node.height
        for member in self.members:
            if member.is_valid_ptr:
                bottom = max(bottom, member.connected_cobject.bottom_y)
        return bottom

    def __repr__(self):
        return self.struct_name + '@' + hex(self.address)


class CObjectManager(object):
    global pat

    def __init__(self, nodz, max_depth, main_address, main_struct_name):
        self.nodz = nodz
        self.max_depth = max_depth
        self.main_address = main_address
        self.main_struct_name = main_struct_name
        self.cobjects = []
        self.add_cobject(main_address, main_struct_name, None)

    def debug_dump(self):
        for cobject in self.cobjects:
            print "CObject : " + hex(cobject.address)
            print "=============================="
            for member in cobject.members:
                print member
            print "=============================="

    def add_cobject(self, address, struct_name, pos, parent_cmember=None):
        if self.is_contain(address):
            return
        cobj = CObject(address, struct_name, pos, cmanager=self, parent_cmember=parent_cmember)
        self.cobjects.append(cobj)
        return cobj

    def search_cmember(self, address):
        obj = self.search_cobject(address)
        return obj.search_cmember(address)

    def search_cobject(self, address):
        for obj in self.cobjects:
            if obj.is_contain(address):
                return obj
        return None

    def is_contain(self, address):
        """

        :param address: Memory address.
        :return: True when object with specified address already added.
        """
        for obj in self.cobjects:
            if obj.is_contain(address):
                return True
        return False

    def auto_layout(self):
        for cobject in self.cobjects:
            print cobject.bottom_y

def object_view_main():
    global nodz #VERY IMPORTANT!!!!
    global max_depth
    global dbg_active
    #check if debugger active

    highlighted = ida_kernwin.get_highlight(ida_kernwin.get_current_widget())
    if highlighted is None:
        print "No highlighted item."
        return
    name,flag = highlighted
    #check if debugger is active
    if flag == 3:
        #name is register name (e.g. RAX)
        try:
            address = idc.get_reg_value(name)
        except:
            address = idc.BADADDR
    else:
        #maybe flag == 1 (what's 2?)
        address = ida_kernwin.str2ea(name)
    s = idc.get_type(address)
    if not s:
        s = ''
    struct_name = ida_kernwin.ask_str(s, 0, "Type struct")
    if not struct_name:
        return


    config_s = {
        "scene_width": 2000,
        "scene_height": 2000,
        "grid_size": 36,
        "antialiasing": True,
        "antialiasing_boost": True,
        "smooth_pixmap": True,

        "node_font": "Arial",
        "node_font_size": 12,
        "attr_font": "Arial",
        "attr_font_size": 10,
        "mouse_bounding_box": 80,

        "node_width": 200,
        "node_height": 25,
        "node_radius": 10,
        "node_border": 2,
        "node_attr_height": 30,
        "connection_width": 2,

        "alternate_value": 20,
        "grid_color": [50, 50, 50, 255],
        "slot_border": [50, 50, 50, 255],
        "non_connectable_color": [100, 100, 100, 255],
        "connection_color": [255, 155, 0, 255],

        "node_default": {
            "bg": [130, 130, 130, 255],
            "border": [50, 50, 50, 255],
            "border_sel": [250, 250, 250, 255],
            "text": [255, 255, 255, 255]
        },

        "attr_default": {
            "bg": [160, 160, 160, 255],
            "text": [220, 220, 220, 255],
            "plug": [255, 155, 0, 255],
            "socket": [255, 155, 0, 255]
        },

        "node_preset_1": {
            "bg": [80, 80, 80, 255],
            "border": [50, 50, 50, 255],
            "border_sel": [170, 80, 80, 255],
            "text": [230, 230, 230, 255]
        },

        "attr_preset_1": {
            "bg": [60, 60, 60, 255],
            "text": [220, 220, 220, 255],
            "plug": [255, 155, 0, 255],
            "socket": [255, 155, 0, 255]
        },

        "attr_preset_2": {
            "bg": [250, 120, 120, 255],
            "text": [220, 220, 220, 255],
            "plug": [255, 155, 0, 255],
            "socket": [255, 155, 0, 255]
        },

        "attr_preset_3": {
            "bg": [160, 160, 160, 255],
            "text": [220, 220, 220, 255],
            "plug": [255, 155, 0, 255],
            "socket": [255, 155, 0, 255]
        }
    }
    #mainwindow = [x for x in QtWidgets.QApplication.topLevelWidgets() if type(x) == QtWidgets.QMainWindow][0]
    #nodz = Nodz(mainwindow, config_s) #will close immediately. fix it.(set parent?)
    nodz = Nodz(None, config_s) #will close immediately. fix it.(set parent?)

    nodz.initialize()
    nodz.show()
    nodz.signal_NodeCreated.connect(on_nodeCreated)
    nodz.signal_NodeDeleted.connect(on_nodeDeleted)
    nodz.signal_NodeEdited.connect(on_nodeEdited)
    nodz.signal_NodeSelected.connect(on_nodeSelected)
    nodz.signal_NodeMoved.connect(on_nodeMoved)

    nodz.signal_AttrCreated.connect(on_attrCreated)
    nodz.signal_AttrDeleted.connect(on_attrDeleted)
    nodz.signal_AttrEdited.connect(on_attrEdited)

    nodz.signal_PlugConnected.connect(on_connected)
    nodz.signal_SocketConnected.connect(on_connected)
    nodz.signal_PlugDisconnected.connect(on_disconnected)
    nodz.signal_SocketDisconnected.connect(on_disconnected)

    nodz.signal_GraphSaved.connect(on_graphSaved)
    nodz.signal_GraphLoaded.connect(on_graphLoaded)
    nodz.signal_GraphCleared.connect(on_graphCleared)
    nodz.signal_GraphEvaluated.connect(on_graphEvaluated)

    nodz.signal_KeyPressed.connect(on_keyPressed)

    try:
        com = CObjectManager(nodz, max_depth, address, struct_name)
        com.auto_layout()
    except NotDefinedObjectException as e:
        print e
        print "Please report to me. X("
        return
    com.debug_dump()

    """
    # Node A
    nodeA = nodz.createNode(name='nodeA', preset='node_preset_1', position=None)

    nodz.createAttribute(node=nodeA, name='Aattr1AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABCD', index=-1, preset='attr_preset_1',
                         plug=True, socket=False, dataType=str)

    nodz.createAttribute(node=nodeA, name='Aattr2', index=-1, preset='attr_preset_1',
                         plug=False, socket=False, dataType=int)

    nodz.createAttribute(node=nodeA, name='Aattr3', index=-1, preset='attr_preset_2',
                         plug=True, socket=True, dataType=int)

    nodz.createAttribute(node=nodeA, name='Aattr4', index=-1, preset='attr_preset_2',
                         plug=True, socket=True, dataType=str)



    # Node B
    nodeB = nodz.createNode(name='nodeB', preset='node_preset_1')

    nodz.createAttribute(node=nodeB, name='Battr1', index=-1, preset='attr_preset_1',
                         plug=True, socket=False, dataType=str)

    nodz.createAttribute(node=nodeB, name='Battr2', index=-1, preset='attr_preset_1',
                         plug=True, socket=False, dataType=int)



    # Node C
    nodeC = nodz.createNode(name='nodeC', preset='node_preset_1')

    nodz.createAttribute(node=nodeC, name='Cattr1', index=-1, preset='attr_preset_1',
                         plug=False, socket=True, dataType=str)

    nodz.createAttribute(node=nodeC, name='Cattr2', index=-1, preset='attr_preset_1',
                         plug=True, socket=False, dataType=int)

    nodz.createAttribute(node=nodeC, name='Cattr3', index=-1, preset='attr_preset_1',
                         plug=True, socket=False, dataType=str)

    nodz.createAttribute(node=nodeC, name='Cattr4', index=-1, preset='attr_preset_2',
                         plug=False, socket=True, dataType=str)

    nodz.createAttribute(node=nodeC, name='Cattr5', index=-1, preset='attr_preset_2',
                         plug=False, socket=True, dataType=int)

    nodz.createAttribute(node=nodeC, name='Cattr6', index=-1, preset='attr_preset_3',
                         plug=True, socket=False, dataType=str)

    nodz.createAttribute(node=nodeC, name='Cattr7', index=-1, preset='attr_preset_3',
                         plug=True, socket=False, dataType=str)

    nodz.createAttribute(node=nodeC, name='Cattr8', index=-1, preset='attr_preset_3',
                         plug=True, socket=False, dataType=int)


    # Please note that this is a local test so once the graph is cleared
    # and reloaded, all the local variables are not valid anymore, which
    # means the following code to alter nodes won't work but saving/loading/
    # clearing/evaluating will.

    # Connection creation
    nodz.createConnection('nodeB', 'Battr2', 'nodeA', 'Aattr3')
    nodz.createConnection('nodeB', 'Battr1', 'nodeA', 'Aattr4')

    # Attributes Edition
    nodz.editAttribute(node=nodeC, index=0, newName=None, newIndex=-1)
    nodz.editAttribute(node=nodeC, index=-1, newName='NewAttrName', newIndex=None)

    # Attributes Deletion
    nodz.deleteAttribute(node=nodeC, index=-1)
    # Nodes Edition
    nodz.editNode(node=nodeC, newName='newNodeName')
    # Nodes Deletion
    nodz.deleteNode(node=nodeC)
    # Graph
    print nodz.evaluateGraph()
    print
    """


    '''
    if app:
        # command line stand alone test... run our own event loop
        app.exec_()
    '''


class object_viewer_handler(idaapi.action_handler_t):
    def __init__(self):
        idaapi.action_handler_t.__init__(self)

    def activate(self, ctx):
        try:
            action = object_view_main()
        except Exception as e:
            print(e)
        return 1

    def update(self, ctx):
        return idaapi.AST_ENABLE_ALWAYS

class UIHook(idaapi.UI_Hooks):
    form_type_list = [idaapi.BWN_DISASM,idaapi.BWN_DUMP,idaapi.BWN_NAMES,idaapi.BWN_PSEUDOCODE,idaapi.BWN_STACK,idaapi.BWN_STKVIEW,idaapi.BWN_STRINGS]
    def __init__(self):
        idaapi.UI_Hooks.__init__(self)

    def finish_populating_tform_popup(self, form, popup):
        form_type = idaapi.get_tform_type(form)

        if form_type in self.form_type_list:
            idaapi.attach_action_to_popup(form, popup, "Object View", None)

class ObjectViewerPlugin(idaapi.plugin_t):
    flags = idaapi.PLUGIN_FIX | idaapi.PLUGIN_HIDE
    comment = "Graphical object viewer for IDA"
    help = ""
    wanted_name = "IDAObjectViewer"
    wanted_hotkey = ""

    def init(self):

        global bits
        info = idaapi.get_inf_structure()
        if info.is_64bit():
            bits = 64
        elif info.is_32bit():
            bits = 32
        else:
            bits = 16 #not tested

        print "Object Viewer Plugin loaded."
        self.ui_hook = UIHook()
        self.ui_hook.hook()
        self.action = idaapi.action_desc_t("Object View", "Object View", object_viewer_handler(), "")
        idaapi.register_action(self.action)
        return idaapi.PLUGIN_KEEP

    def run(self, arg):
        pass

    def term(self):
        self.ui_hook.unhook()
        idaapi.unregister_action("Object View")
        pass

def PLUGIN_ENTRY():
    return ObjectViewerPlugin()