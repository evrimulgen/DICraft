import math
import random
import time

from collections import deque
from pyglet import image
from pyglet.gl import *
from pyglet.graphics import TextureGroup
from pyglet.window import key

import saveModule
import sys

sys.setrecursionlimit(64000)

# Size of sectors used to ease block loading.
SECTOR_SIZE = 150

# default cube size is 0.5
# not changeable, yet
CUBE_SIZE = 0.5

# distance for interaction with cubes
EDIT_DISTANCE = 42


def cube_vertices(x, y, z, n):
	""" Return the vertices of the cube at position x, y, z with size 2*n.

	"""
	return [
		x-n,y+n,z-n, x-n,y+n,z+n, x+n,y+n,z+n, x+n,y+n,z-n,  # top
		x-n,y-n,z-n, x+n,y-n,z-n, x+n,y-n,z+n, x-n,y-n,z+n,  # bottom
		x-n,y-n,z-n, x-n,y-n,z+n, x-n,y+n,z+n, x-n,y+n,z-n,  # left
		x+n,y-n,z+n, x+n,y-n,z-n, x+n,y+n,z-n, x+n,y+n,z+n,  # right
		x-n,y-n,z+n, x+n,y-n,z+n, x+n,y+n,z+n, x-n,y+n,z+n,  # front
		x+n,y-n,z-n, x-n,y-n,z-n, x-n,y+n,z-n, x+n,y+n,z-n,  # back
	]


def tex_coord(x, y, n=200):
	""" Return the bounding vertices of the texture square.
	
	Parameters:
	n : the NUMBER of texture elements on the X/WITH axis of the image
	"""
	m = 1.0 / n
	dx = x * m
	dy = y * m
	return dx, dy, dx + m, dy, dx + m, dy + m, dx, dy + m


def tex_coords(top, bottom, side):
	""" Return a list of the texture squares for the top, bottom and side.

	"""
	top = tex_coord(*top)
	bottom = tex_coord(*bottom)
	side = tex_coord(*side)
	result = []
	result.extend(top)
	result.extend(bottom)
	result.extend(side * 4)
	return result

def tex_coords_simple(xCoord):
	""" Return a list of the texture squares for the top, bottom and side.

	"""
	allSides = (xCoord, 0)
	
	top = tex_coord(*allSides)
	bottom = tex_coord(*allSides)
	side = tex_coord(*allSides)
	result = []
	result.extend(top)
	result.extend(bottom)
	result.extend(side * 4)
	return result

TEXTURE_PATH = 'texture.png'

#GRASS = tex_coords((1, 0), (0, 1), (0, 0))
#SAND = tex_coords((1, 1), (1, 1), (1, 1))
#BRICK = tex_coords((2, 0), (2, 0), (2, 0))
#STONE = tex_coords((2, 1), (2, 1), (2, 1))

MATERIALS = []
for i in xrange(100):
	MATERIALS.append(tex_coords_simple(i))



FACES = [
	( 0, 1, 0),
	( 0,-1, 0),
	(-1, 0, 0),
	( 1, 0, 0),
	( 0, 0, 1),
	( 0, 0,-1),
]


def normalize(position):
	""" Accepts `position` of arbitrary precision and returns the block
	containing that position.

	Parameters
	----------
	position : tuple of len 3

	Returns
	-------
	block_position : tuple of ints of len 3

	"""
	x, y, z = position
	x, y, z = (int(round(x)), int(round(y)), int(round(z)))
	return (x, y, z)


def sectorize(position):
	""" Returns a tuple representing the sector for the given `position`.

	Parameters
	----------
	position : tuple of len 3

	Returns
	-------
	sector : tuple of len 3

	"""
	x, y, z = normalize(position)
	x, y, z = x / SECTOR_SIZE, y / SECTOR_SIZE, z / SECTOR_SIZE
	return (x, 0, z)


class Model(object):

	def __init__(self):

		# A Batch is a collection of vertex lists for batched rendering.
		self.batch = pyglet.graphics.Batch()

		# A TextureGroup manages an OpenGL texture.
		self.group = TextureGroup(image.load(TEXTURE_PATH).get_texture())

		# A mapping from position to the texture of the block at that position.
		# This defines all the blocks that are currently in the world.
		self.world = {}

		# Same mapping as `world` but only contains blocks that are shown.
		self.shown = {}

		# Mapping from position to a pyglet `VertextList` for all shown blocks.
		self._shown = {}

		# Mapping from sector to a list of positions inside that sector.
		self.sectors = {}

		# Simple function queue implementation. The queue is populated with
		# _show_block() and _hide_block() calls
		self.queue = deque()
		
		# a module to save and load the world
		self.saveModule = saveModule.saveModule()

		self._initialize()

	def _initialize(self):
		""" Initialize the world by placing all the blocks.

		"""
		
		if self.saveModule.hasSaveFile() == True:
			self.saveModule.loadWorld(self)
		else:
			for x in xrange(len(MATERIALS)):
				self.add_block((x, 0, 0), MATERIALS[x], immediate=False)
				
			for z in xrange(len(MATERIALS)):
				self.add_block((0, z, 1), MATERIALS[z], immediate=False)
				
			for y in xrange(len(MATERIALS)):
				self.add_block((0, 2, y), MATERIALS[y], immediate=False)

	def hit_test(self, position, vector, max_distance=8):
		""" Line of sight search from current position. If a block is
		intersected it is returned, along with the block previously in the line
		of sight. If no block is found, return None, None.

		Parameters
		----------
		position : tuple of len 3
			The (x, y, z) position to check visibility from.
		vector : tuple of len 3
			The line of sight vector.
		max_distance : int
			How many blocks away to search for a hit.

		"""
		m = 8
		x, y, z = position
		dx, dy, dz = vector
		previous = None
		for _ in xrange(max_distance * m):
			key = normalize((x, y, z))
			if key != previous and key in self.world:
				return key, previous
			previous = key
			x, y, z = x + dx / m, y + dy / m, z + dz / m
		return None, None

	def get_empy_space(self, position, vector, max_distance=8):
		""" returns the position of an empty space in range
		return none if there is no empty space
		
		Parameters
		----------
		position : tuple of len 3
			The (x, y, z) position to check visibility from.
		vector : tuple of len 3
			The line of sight vector.
		max_distance : int
			How many blocks away to search for a hit.
			
		"""
		m = 8
		x, y, z = position
		dx, dy, dz = vector
		previous = None
		
		rangeCounter = 0
		for _ in xrange(max_distance * m):
			rangeCounter += 1
			if rangeCounter == max_distance * m:
				key = normalize((x, y, z))
				if not key in self.world:
					return key
			x, y, z = x + dx / m, y + dy / m, z + dz / m
		return None
		

	def exposed(self, position):
		""" Returns False is given `position` is surrounded on all 6 sides by
		blocks, True otherwise.

		"""
		x, y, z = position
		for dx, dy, dz in FACES:
			if (x + dx, y + dy, z + dz) not in self.world:
				return True
		return False

	def add_block(self, position, texture, immediate=True):
		""" Add a block with the given `texture` and `position` to the world.

		Parameters
		----------
		position : tuple of len 3
			The (x, y, z) position of the block to add.
		texture : list of len 3
			The coordinates of the texture squares. Use `tex_coords()` to
			generate.
		immediate : bool
			Whether or not to draw the block immediately.

		"""
		if position in self.world:
			self.remove_block(position, immediate)
		self.world[position] = texture
		self.sectors.setdefault(sectorize(position), []).append(position)
		if immediate:
			if self.exposed(position):
				self.show_block(position)
			self.check_neighbors(position)

	def remove_block(self, position, immediate=True):
		""" Remove the block at the given `position`.

		Parameters
		----------
		position : tuple of len 3
			The (x, y, z) position of the block to remove.
		immediate : bool
			Whether or not to immediately remove block from canvas.

		"""
		del self.world[position]
		self.sectors[sectorize(position)].remove(position)
		if immediate:
			if position in self.shown:
				self.hide_block(position)
			self.check_neighbors(position)
		
	def _get_neighbor_blocks(self, block, neighbors):
		""" Finds the surrounding blocks of given block.
			WARNING: crashes after too many recursive calls!

		Parameters
		----------
		block : tuple of len 3
			The (x, y, z) position of the block.
		neighbors : tuple
			combined list of neighbors

		"""
		my_neighbors = neighbors
		my_neighbors.append(block)
		x, y, z = block
		for dx, dy, dz in FACES:
			key = (x + dx, y + dy, z + dz)
			if key in self.world and not key in my_neighbors:
				my_neighbors + self._get_neighbor_blocks(key, my_neighbors)
				
		return my_neighbors
		
	def remove_block_isle(self, start_block):
		""" Removing a bunch of blocks that belongs to each other

		Parameters
		----------
		start_block : tuple of len 3
			The (x, y, z) position of the start block to remove.
		"""

		block_collection = []
		if start_block:
			x, y, z = start_block
			block_collection + self._get_neighbor_blocks(start_block, block_collection)
		
		print "removing blocks:", len(block_collection)
		for b in block_collection:
			self.remove_block(b)

	def check_neighbors(self, position):
		""" Check all blocks surrounding `position` and ensure their visual
		state is current. This means hiding blocks that are not exposed and
		ensuring that all exposed blocks are shown. Usually used after a block
		is added or removed.

		"""
		x, y, z = position
		for dx, dy, dz in FACES:
			key = (x + dx, y + dy, z + dz)
			if key not in self.world:
				continue
			if self.exposed(key):
				if key not in self.shown:
					self.show_block(key)
			else:
				if key in self.shown:
					self.hide_block(key)

	def show_block(self, position, immediate=True):
		""" Show the block at the given `position`. This method assumes the
		block has already been added with add_block()

		Parameters
		----------
		position : tuple of len 3
			The (x, y, z) position of the block to show.
		immediate : bool
			Whether or not to show the block immediately.

		"""
		texture = self.world[position]
		self.shown[position] = texture
		if immediate:
			self._show_block(position, texture)
		else:
			self._enqueue(self._show_block, position, texture)

	def _show_block(self, position, texture):
		""" Private implementation of the `show_block()` method.

		Parameters
		----------
		position : tuple of len 3
			The (x, y, z) position of the block to show.
		texture : list of len 3
			The coordinates of the texture squares. Use `tex_coords()` to
			generate.

		"""
		x, y, z = position
		vertex_data = cube_vertices(x, y, z, CUBE_SIZE)
		texture_data = list(texture)
		# create vertex list
		# FIXME Maybe `add_indexed()` should be used instead
		self._shown[position] = self.batch.add(24, GL_QUADS, self.group,
			('v3f/static', vertex_data),
			('t2f/static', texture_data))

	def hide_block(self, position, immediate=True):
		""" Hide the block at the given `position`. Hiding does not remove the
		block from the world.

		Parameters
		----------
		position : tuple of len 3
			The (x, y, z) position of the block to hide.
		immediate : bool
			Whether or not to immediately remove the block from the canvas.

		"""
		self.shown.pop(position)
		if immediate:
			self._hide_block(position)
		else:
			self._enqueue(self._hide_block, position)

	def _hide_block(self, position):
		""" Private implementation of the 'hide_block()` method.

		"""
		self._shown.pop(position).delete()

	def show_sector(self, sector):
		""" Ensure all blocks in the given sector that should be shown are
		drawn to the canvas.

		"""
		for position in self.sectors.get(sector, []):
			if position not in self.shown and self.exposed(position):
				self.show_block(position, False)

	def hide_sector(self, sector):
		""" Ensure all blocks in the given sector that should be hidden are
		removed from the canvas.

		"""
		for position in self.sectors.get(sector, []):
			if position in self.shown:
				self.hide_block(position, False)

	def change_sectors(self, before, after):
		""" Move from sector `before` to sector `after`. A sector is a
		contiguous x, y sub-region of world. Sectors are used to speed up
		world rendering.

		"""	
		before_set = set()
		after_set = set()
		pad = 4
		for dx in xrange(-pad, pad + 1):
			for dy in [0]:  # xrange(-pad, pad + 1):
				for dz in xrange(-pad, pad + 1):
					if dx ** 2 + dy ** 2 + dz ** 2 > (pad + 1) ** 2:
						continue
					if before:
						x, y, z = before
						before_set.add((x + dx, y + dy, z + dz))
					if after:
						x, y, z = after
						after_set.add((x + dx, y + dy, z + dz))
		show = after_set - before_set
		hide = before_set - after_set
		for sector in show:
			self.show_sector(sector)
		for sector in hide:
			self.hide_sector(sector)

	def _enqueue(self, func, *args):
		""" Add `func` to the internal queue.

		"""
		self.queue.append((func, args))

	def _dequeue(self):
		""" Pop the top function from the internal queue and call it.

		"""
		func, args = self.queue.popleft()
		func(*args)

	def process_queue(self):
		""" Process the entire queue while taking periodic breaks. This allows
		the game loop to run smoothly. The queue contains calls to
		_show_block() and _hide_block() so this method should be called if
		add_block() or remove_block() was called with immediate=False

		"""
		start = time.clock()
		while self.queue and time.clock() - start < 1 / 60.0:
			self._dequeue()

	def process_entire_queue(self):
		""" Process the entire queue with no breaks.

		"""
		while self.queue:
			self._dequeue()


class Window(pyglet.window.Window):

	def __init__(self, *args, **kwargs):
		super(Window, self).__init__(*args, **kwargs)

		# Whether or not the window exclusively captures the mouse.
		self.exclusive = False

		# When flying gravity has no effect and speed is increased.
		self.flying = True

		# First element is -1 when moving forward, 1 when moving back, and 0
		# otherwise. The second element is -1 when moving left, 1 when moving
		# right, and 0 otherwise.
		self.strafe = [0, 0]

		# Current (x, y, z) position in the world, specified with floats.
		self.position = (-2, -2, 1)

		# First element is rotation of the player in the x-z plane (ground
		# plane) measured from the z-axis down. The second is the rotation
		# angle from the ground plane up.
		self.rotation = (100, 0)

		# Which sector the player is currently in.
		self.sector = None

		# The crosshairs at the center of the screen.
		self.reticle = None

		# Velocity in the y (upward) direction.
		self.dy = 0

		# A list of blocks the player can place. Hit num keys to cycle.
		#self.inventory = [BRICK, GRASS, SAND]
		self.inventory = []
		for i in range(0, len(MATERIALS), 10):
			#print "inventory:",i, MATERIALS[i]
			self.inventory.append(MATERIALS[i])

		# The current block the user can place. Hit num keys to cycle.
		self.block = self.inventory[0]

		# Convenience list of num keys.
		self.num_keys = [
			key._1, key._2, key._3, key._4, key._5,
			key._6, key._7, key._8, key._9, key._0]

		# Instance of the model that handles the world.
		self.model = Model()

		# The label that is displayed in the top left of the canvas.
		self.label = pyglet.text.Label('', font_name='Arial', font_size=16,
			x=10, y=self.height - 10, anchor_x='left', anchor_y='top',
			color=(0, 0, 0, 255))

		# This call schedules the `update()` method to be called 60 times a
		# second. This is the main game event loop.
		pyglet.clock.schedule_interval(self.update, 1.0 / 60)
		
		# start in window mode!
		self.fullScreen = False

	def set_exclusive_mouse(self, exclusive):
		""" If `exclusive` is True, the game will capture the mouse, if False
		the game will ignore the mouse.

		"""
		super(Window, self).set_exclusive_mouse(exclusive)
		self.exclusive = exclusive

	def get_sight_vector(self):
		""" Returns the current line of sight vector indicating the direction
		the player is looking.

		"""
		x, y = self.rotation
		m = math.cos(math.radians(y))
		dy = math.sin(math.radians(y))
		dx = math.cos(math.radians(x - 90)) * m
		dz = math.sin(math.radians(x - 90)) * m
		return (dx, dy, dz)

	def get_motion_vector(self):
		""" Returns the current motion vector indicating the velocity of the
		player.

		Returns
		-------
		vector : tuple of len 3
			Tuple containing the velocity in x, y, and z respectively.

		"""
		if any(self.strafe):
			x, y = self.rotation
			strafe = math.degrees(math.atan2(*self.strafe))
			if self.flying:
				m = math.cos(math.radians(y))
				dy = math.sin(math.radians(y))
				if self.strafe[1]:
					dy = 0.0
					m = 1
				if self.strafe[0] > 0:
					dy *= -1
				dx = math.cos(math.radians(x + strafe)) * m
				dz = math.sin(math.radians(x + strafe)) * m
			else:
				dy = 0.0
				dx = math.cos(math.radians(x + strafe))
				dz = math.sin(math.radians(x + strafe))
		else:
			dy = 0.0
			dx = 0.0
			dz = 0.0
		return (dx, dy, dz)

	def update(self, dt):
		""" This method is scheduled to be called repeatedly by the pyglet
		clock.

		Parameters
		----------
		dt : float
			The change in time since the last call.

		"""
		self.model.process_queue()
		sector = sectorize(self.position)
		if sector != self.sector:
			self.model.change_sectors(self.sector, sector)
			if self.sector is None:
				self.model.process_entire_queue()
			self.sector = sector
		m = 8
		dt = min(dt, 0.2)
		for _ in xrange(m):
			self._update(dt / m)

	def _update(self, dt):
		""" Private implementation of the `update()` method. This is where most
		of the motion logic lives, along with gravity and collision detection.

		Parameters
		----------
		dt : float
			The change in time since the last call.

		"""
		# walking
		speed = 15 if self.flying else 5
		d = dt * speed
		dx, dy, dz = self.get_motion_vector()
		dx, dy, dz = dx * d, dy * d, dz * d
		# gravity
		if not self.flying:
			# g force, should be = jump_speed * 0.5 / max_jump_height
			self.dy -= dt * 0.044
			self.dy = max(self.dy, -0.5)  # terminal velocity
			dy += self.dy
		elif self.dy != 0.0:
			dy += self.dy / speed
				
		# collisions
		x, y, z = self.position
		#x, y, z = self.collide((x + dx, y + dy, z + dz), 2)
		# disable collision
		#self.position = (x, y, z)
		self.position = (x + dx, y + dy, z + dz)

	def collide(self, position, height):
		""" Checks to see if the player at the given `position` and `height`
		is colliding with any blocks in the world.

		Parameters
		----------
		position : tuple of len 3
			The (x, y, z) position to check for collisions at.
		height : int or float
			The height of the player.

		Returns
		-------
		position : tuple of len 3
			The new position of the player taking into account collisions.

		"""	  
		pad = 0.25
		p = list(position)
		np = normalize(position)
		for face in FACES:  # check all surrounding blocks
			for i in xrange(3):  # check each dimension independently
				if not face[i]:
					continue
				d = (p[i] - np[i]) * face[i]
				if d < pad:
					continue
				for dy in xrange(height):  # check each height
					op = list(np)
					op[1] -= dy
					op[i] += face[i]
					op = tuple(op)
					if op not in self.model.world:
						continue
					p[i] -= (d - pad) * face[i]
					if face == (0, -1, 0) or face == (0, 1, 0):
						self.dy = 0
					break
		return tuple(p)

	def on_mouse_press(self, x, y, button, modifiers):
		""" Called when a mouse button is pressed. See pyglet docs for button
		amd modifier mappings.

		Parameters
		----------
		x, y : int
			The coordinates of the mouse click. Always center of the screen if
			the mouse is captured.
		button : int
			Number representing mouse button that was clicked. 1 = left button,
			4 = right button.
		modifiers : int
			Number representing any modifying keys that were pressed when the
			mouse button was clicked.

		"""
		if self.exclusive:
			vector = self.get_sight_vector()
			block, previous = self.model.hit_test(self.position, vector, EDIT_DISTANCE)
			if button == pyglet.window.mouse.LEFT:
				if block:
					texture = self.model.world[block]
					self.model.remove_block(block)
			else:
				if previous:
					self.model.add_block(previous, self.block)
				else:
					emptySpace = self.model.get_empy_space(self.position, vector)
					if emptySpace:
						self.model.add_block(emptySpace, self.block)
		else:
			self.set_exclusive_mouse(True)

	def on_mouse_motion(self, x, y, dx, dy):
		""" Called when the player moves the mouse.

		Parameters
		----------
		x, y : int
			The coordinates of the mouse click. Always center of the screen if
			the mouse is captured.
		dx, dy : float
			The movement of the mouse.

		"""
		if self.exclusive:
			m = 0.15
			x, y = self.rotation
			x, y = x + dx * m, y + dy * m
			y = max(-90, min(90, y))
			self.rotation = (x, y)

	def on_key_press(self, symbol, modifiers):
		""" Called when the player presses a key. See pyglet docs for key
		mappings.

		Parameters
		----------
		symbol : int
			Number representing the key that was pressed.
		modifiers : int
			Number representing any modifying keys that were pressed.

		"""
		if symbol == key.W:
			self.strafe[0] -= 1
		elif symbol == key.S:
			self.strafe[0] += 1
		elif symbol == key.A:
			self.strafe[1] -= 1
		elif symbol == key.D:
			self.strafe[1] += 1
		elif symbol == key.SPACE:
			#if self.dy == 0:
			self.dy = 1.0  # jump speed
		elif symbol == key.LCTRL:
			#if self.dy == 0:
			self.dy = -1.0
		elif symbol == key.DELETE:
			vector = self.get_sight_vector()
			block = self.model.hit_test(self.position, vector, EDIT_DISTANCE)[0]
			self.model.remove_block_isle(block)
		elif symbol == key.F5:
			self.model.saveModule.saveWorld(self.model)
		elif symbol == key.F6:
			#self.model.saveModule.exportOpenScad(self.model)
			self.model.saveModule.exportStl(self.model)
		elif symbol == key.ESCAPE:
			exit()
		elif symbol == key.F1:
			self.set_exclusive_mouse(False)
		elif symbol == key.TAB:
			self.flying = not self.flying
		elif symbol in self.num_keys:
			index = (symbol - self.num_keys[0]) % len(self.inventory)
			print index
			self.block = self.inventory[index]

	def on_key_release(self, symbol, modifiers):
		""" Called when the player releases a key. See pyglet docs for key
		mappings.

		Parameters
		----------
		symbol : int
			Number representing the key that was pressed.
		modifiers : int
			Number representing any modifying keys that were pressed.

		"""
		if symbol == key.W:
			self.strafe[0] += 1
		elif symbol == key.S:
			self.strafe[0] -= 1
		elif symbol == key.A:
			self.strafe[1] += 1
		elif symbol == key.D:
			self.strafe[1] -= 1
		elif symbol == key.SPACE:
			self.dy = 0.0 
		elif symbol == key.LCTRL:
			self.dy = 0.0
		elif symbol == key.F:  # only on release, prevent alltime switch
			self.fullScreen = not self.fullScreen
			self.set_fullscreen(fullscreen = self.fullScreen)
			self.set_exclusive_mouse(False)
			self.set_exclusive_mouse(True)
			
	def on_resize(self, width, height):
		""" Called when the window is resized to a new `width` and `height`.

		"""
		# label
		self.label.y = height - 10
		# reticle
		if self.reticle:
			self.reticle.delete()
		x, y = self.width / 2, self.height / 2
		n = 10
		self.reticle = pyglet.graphics.vertex_list(4,
			('v2i', (x - n, y, x + n, y, x, y - n, x, y + n))
		)

	def set_2d(self):
		""" Configure OpenGL to draw in 2d.

		"""
		width, height = self.get_size()
		glDisable(GL_DEPTH_TEST)
		glViewport(0, 0, width, height)
		glMatrixMode(GL_PROJECTION)
		glLoadIdentity()
		glOrtho(0, width, 0, height, -1, 1)
		glMatrixMode(GL_MODELVIEW)
		glLoadIdentity()

	def set_3d(self):
		""" Configure OpenGL to draw in 3d.

		"""
		width, height = self.get_size()
		glEnable(GL_DEPTH_TEST)
		glViewport(0, 0, width, height)
		glMatrixMode(GL_PROJECTION)
		glLoadIdentity()
		#gluPerspective(45.0f,(GLfloat)width/(GLfloat)height,near distance,far distance);
		#gluPerspective(65.0, width / float(height), 0.1, 60.0)
		gluPerspective(65.0, width / float(height), 0.1, 6000.0)
		glMatrixMode(GL_MODELVIEW)
		glLoadIdentity()
		
		#glDepthMask(GL_FALSE)
		#drawSkybox()
		#glDepthMask(GL_TRUE)
		
		x, y = self.rotation
		#http://wiki.delphigl.com/index.php/glRotate
		#procedure glRotatef(angle: TGLfloat; x: TGLfloat; y: TGLfloat; z: TGLfloat); 
		glRotatef(x, 0, 1, 0)
		glRotatef(-y, math.cos(math.radians(x)), 0, math.sin(math.radians(x)))
		x, y, z = self.position
		glTranslatef(-x, -y, -z)

	def on_draw(self):
		""" Called by pyglet to draw the canvas.

		"""
		self.clear()
		self.set_3d()
		glColor3d(1, 1, 1)
		self.model.batch.draw()
		self.draw_focused_block()
		self.set_2d()
		self.draw_label()
		self.draw_reticle()

	def draw_focused_block(self):
		""" Draw black edges around the block that is currently under the
		crosshairs.

		"""
		vector = self.get_sight_vector()
		block = self.model.hit_test(self.position, vector, EDIT_DISTANCE)[0]
		if block:
			x, y, z = block
			vertex_data = cube_vertices(x, y, z, CUBE_SIZE + 0.01)
			glColor3d(255, 255, 21)
			# white focus
			pyglet.graphics.draw(24, GL_QUADS, ('v3f/static', vertex_data))
			# borderlines
			glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
			glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

	def draw_label(self):
		""" Draw the label in the top left of the screen.

		"""
		x, y, z = self.position
		self.label.text = '%02d (%.2f, %.2f, %.2f) %d / %d' % (
			pyglet.clock.get_fps(), x, y, z,
			len(self.model._shown), len(self.model.world))
		self.label.draw()

	def draw_reticle(self):
		""" Draw the crosshairs in the center of the screen.

		"""
		glColor3d(0, 0, 0)
		self.reticle.draw(GL_LINES)



def log(txt):
	print(time.strftime("%d-%m-%Y %H:%M:%S|", time.gmtime()) + str(txt) ) 


def setup():
	""" Basic OpenGL configuration.

	"""
	glClearColor(0.5, 0.69, 1.0, 1)
	glEnable(GL_CULL_FACE)
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)


def main():
	window = Window(width=800, height=600, caption='DICraft', resizable=True)
	#window = Window(fullscreen=True, caption='DICraft')
	#window.set_exclusive_mouse(True)
	setup()
	pyglet.app.run()


if __name__ == '__main__':
	main()
