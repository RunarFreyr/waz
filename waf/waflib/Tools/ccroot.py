#!/usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005-2010 (ita)

"base for all c/c++ programs and libraries"

import os, sys, re
from waflib import TaskGen, Task, Utils, Logs, Build, Options, Node, Errors
from waflib.Logs import error, debug, warn
from waflib.TaskGen import after, before, feature, taskgen_method
from waflib.Tools import c_aliases, c_preproc, c_config, c_asm, c_osx, c_tests
from waflib.Configure import conf

USELIB_VARS = Utils.defaultdict(set)
USELIB_VARS['c']   = set(['INCLUDES', 'FRAMEWORKPATH', 'DEFINES', 'CCDEPS', 'CFLAGS'])
USELIB_VARS['cxx'] = set(['INCLUDES', 'FRAMEWORKPATH', 'DEFINES', 'CXXDEPS', 'CXXFLAGS'])
USELIB_VARS['d']   = set(['INCLUDES', 'DFLAGS'])

USELIB_VARS['cprogram'] = USELIB_VARS['cxxprogram'] = set(['LIB', 'STLIB', 'LIBPATH', 'STLIBPATH', 'LINKFLAGS', 'RPATH', 'LINKDEPS', 'FRAMEWORK', 'FRAMEWORKPATH'])
USELIB_VARS['cshlib']   = USELIB_VARS['cxxshlib']   = set(['LIB', 'STLIB', 'LIBPATH', 'STLIBPATH', 'LINKFLAGS', 'RPATH', 'LINKDEPS', 'FRAMEWORK', 'FRAMEWORKPATH'])
USELIB_VARS['cstlib']   = USELIB_VARS['cxxstlib']   = set(['ARFLAGS', 'LINKDEPS'])

USELIB_VARS['dprogram'] = set(['LIB', 'STLIB', 'LIBPATH', 'STLIBPATH', 'LINKFLAGS', 'RPATH', 'LINKDEPS'])
USELIB_VARS['dshlib']   = set(['LIB', 'STLIB', 'LIBPATH', 'STLIBPATH', 'LINKFLAGS', 'RPATH', 'LINKDEPS'])
USELIB_VARS['dstlib']   = set(['ARFLAGS', 'LINKDEPS'])

USELIB_VARS['go'] = set(['GOCFLAGS'])
USELIB_VARS['goprogram'] = set(['GOLFLAGS'])

USELIB_VARS['asm'] = set(['ASFLAGS'])

# =================================================================================================

@taskgen_method
def create_compiled_task(self, name, node):
	"""
	creates the compilation task: c, cxx, asm, ...
	the task is appended to the list 'compiled_tasks' which is used by
	'apply_link'
	"""
	out = '%s.%d.o' % (node.name, self.idx)
	task = self.create_task(name, node, node.parent.find_or_declare(out))
	try:
		self.compiled_tasks.append(task)
	except AttributeError:
		self.compiled_tasks = [task]
	return task

@taskgen_method
def to_incnodes(self, inlst):
	"""
	return a list of node objects from a list of includes, assuming
	self.includes is a space-delimited string or a list of string/nodes

	paths are relative to the task generator path, except if they begin by #
	in which case they are relative to the top directory (bld.srcnode)
	"""
	lst = []
	seen = set([])
	for x in self.to_list(inlst):
		if x in seen:
			continue
		seen.add(x)

		if isinstance(x, Node.Node):
			lst.append(x)
		else:
			if os.path.isabs(x):
				lst.append(self.bld.root.find_dir(x))
			else:
				if x[0] == '#':
					lst.append(self.bld.bldnode.find_dir(x[1:]))
					lst.append(self.bld.srcnode.find_dir(x[1:]))
				else:
					lst.append(self.path.get_bld().find_dir(x))
					lst.append(self.path.find_dir(x))
	# TODO this is ugly
	lst = [x for x in lst if x]
	return lst

@feature('c', 'cxx', 'd', 'go', 'asm', 'fc', 'includes')
@after('propagate_uselib_vars', 'process_source')
def apply_incpaths(self):
	"""used by the scanner
	after processing the uselib for INCLUDES
	after process_source because some processing may add include paths
	"""

	lst = self.to_incnodes(self.to_list(getattr(self, 'includes', [])) + self.env['INCLUDES'])
	self.includes_nodes = lst
	self.env['INCPATHS'] = [x.abspath() for x in lst]

class link_task(Task.Task):
	"""base class for all link tasks (c_link, cxx_link, etc)"""
	color   = 'YELLOW'
	inst_to = None
	chmod   = Utils.O644

	def add_target(self, target):
		if isinstance(target, str):
			pattern = self.env[self.__class__.__name__ + '_PATTERN']
			if not pattern:
				pattern = '%s'
			folder, name = os.path.split(target)

			if self.__class__.__name__.find('shlib') > 0:
				if self.env.DEST_BINFMT == 'pe' and getattr(self.generator, 'vnum', None):
					# include the version in the dll file name,
					# the import lib file name stays unversionned.
					name = name + '-' + self.generator.vnum.split('.')[0]

			tmp = folder + os.sep + pattern % name
			target = self.generator.path.find_or_declare(tmp)
		self.set_outputs(target)

class stlink_task(link_task):
	"""link static libraries (with ar)"""
	run_str = '${AR} ${ARFLAGS} ${AR_TGT_F}${TGT} ${AR_SRC_F}${SRC}'

def rm_tgt(cls):
	old = cls.run
	def wrap(self):
		try: os.remove(self.outputs[0].abspath())
		except OSError: pass
		return old(self)
	setattr(cls, 'run', wrap)
rm_tgt(stlink_task)

@feature('c', 'cxx', 'd', 'go', 'fc')
@after('process_source')
def apply_link(self):
	"""executes after process_source for collecting 'compiled_tasks' and creating a 'link_task'"""

	for x in self.features:
		if x == 'cprogram' and 'cxx' in self.features: # limited compat
			x = 'cxxprogram'
		elif x == 'cshlib' and 'cxx' in self.features:
			x = 'cxxshlib'

		if x in Task.classes:
			if issubclass(Task.classes[x], link_task):
				link = x
				break
	else:
		return

	objs = [t.outputs[0] for t in getattr(self, 'compiled_tasks', [])]
	self.link_task = self.create_task(link, objs)
	self.link_task.add_target(self.target)

	if getattr(self.bld, 'is_install', None):
		# remember that the install paths are given by the task generators
		try:
			inst_to = self.install_path
		except AttributeError:
			inst_to = self.link_task.__class__.inst_to
		if inst_to:
			# install a copy of the node list we have at this moment (implib not added)
			self.install_task = self.bld.install_files(inst_to, self.link_task.outputs[:], env=self.env, chmod=self.link_task.chmod)

@taskgen_method
def use_rec(self, name, objects=True, stlib=True):
	"""
	process the use keyword, recursively
	"""
	if name in self.seen_libs:
		return
	else:
		self.seen_libs.add(name)

	get = self.bld.get_tgen_by_name
	try:
		y = get(name)
	except Errors.WafError:
		self.uselib.append(name)
		return

	y.post()
	has_link = getattr(y, 'link_task', None)
	is_static = has_link and isinstance(y.link_task, stlink_task)

	# depth-first processing
	for x in self.to_list(getattr(y, 'use', [])):
		self.use_rec(x, objects and not has_link, stlib and (is_static or not has_link))

	# link task and flags
	if getattr(self, 'link_task', None):
		if has_link:
			if (not is_static) or (is_static and stlib):
				var = isinstance(y.link_task, stlink_task) and 'STLIB' or 'LIB'
				self.env.append_value(var, [y.target[y.target.rfind(os.sep) + 1:]])

				# the order
				self.link_task.set_run_after(y.link_task)

				# for the recompilation
				self.link_task.dep_nodes.extend(y.link_task.outputs)

				# add the link path too
				tmp_path = y.link_task.outputs[0].parent.bldpath()
				if not tmp_path in self.env[var + 'PATH']:
					self.env.prepend_value(var + 'PATH', [tmp_path])
		elif objects:
			for t in getattr(y, 'compiled_tasks', []):
				self.link_task.inputs.extend(t.outputs)

	# add ancestors uselib too - but only propagate those that have no staticlib defined
	for v in self.to_list(getattr(y, 'uselib', [])):
		if not self.env['STLIB_' + v]:
			if not v in self.uselib:
				self.uselib.insert(0, v)

	# if the library task generator provides 'export_incdirs', add to the include path
	# the export_incdirs must be a list of paths relative to the other library
	if getattr(y, 'export_includes', None):
		self.includes.extend(y.to_incnodes(y.export_includes))

@feature('c', 'cxx', 'd', 'use', 'fc')
@before('apply_incpaths', 'propagate_uselib_vars')
@after('apply_link', 'process_source')
def process_use(self):
	"""
	process the 'use' attribute which is like uselib+uselib_local+add_objects
	execute after apply_link because of the execution order must be set on 'link_task'

	propagation rules:
	a static library is found -> propagation on anything stops
	a shared library (non-static) is found -> propagation continues, but objects are not added
	"""

	self.uselib = self.to_list(getattr(self, 'uselib', []))
	self.includes = self.to_list(getattr(self, 'includes', []))
	names = self.to_list(getattr(self, 'use', []))
	self.seen_libs = set([])

	for x in names:
		self.use_rec(x)

@taskgen_method
def get_uselib_vars(self):
	"helper function"
	_vars = set([])
	for x in self.features:
		if x in USELIB_VARS:
			_vars |= USELIB_VARS[x]
	return _vars

@feature('c', 'cxx', 'd', 'fc', 'cs', 'uselib')
@after('process_use')
def propagate_uselib_vars(self):
	"""process uselib variables for adding flags"""
	_vars = self.get_uselib_vars()
	env = self.env

	# 1. add the attributes defined in a lowercase manner such as obj.cxxflags
	for x in _vars:

		# TODO for debugging, detect the invalid variables such as ldflags, ccflag, header, etc (plurals, capitalization, ...)
		y = x.lower()
		env.append_unique(x, self.to_list(getattr(self, y, [])))

	# 2. each compiler defines variables like 'CXXFLAGS_cshlib', 'LINKFLAGS_cshlib', etc
	# so when we make a task generator of the type cshlib, CXXFLAGS are modified accordingly
	# the order was reversed compared to waf 1.5: cshlib_LINKFLAGS -> LINKFLAGS_cshlib
	for x in self.features:
		for var in _vars:
			compvar = '%s_%s' % (var, x)
			env.append_value(var, env[compvar])

	# 3. the case of the libs defined outside
	for x in self.to_list(getattr(self, 'uselib', [])):
		for v in _vars:
			env.append_value(v, env[v + '_' + x])

# ============ the code above must not know anything about import libs ==========

@feature('cshlib', 'cxxshlib')
@after('apply_link')
@before('apply_lib_vars', 'apply_objdeps')
def apply_implib(self):
	"""On mswindows, handle dlls and their import libs
	the .dll.a is the import lib and it is required for linking so it is installed too
	"""
	if not self.env.DEST_BINFMT == 'pe':
		return

	dll = self.link_task.outputs[0]
	implib = self.env['implib_PATTERN'] % os.path.split(self.target)[1]
	implib = dll.parent.find_or_declare(implib)
	self.env.append_value('LINKFLAGS', self.env['IMPLIB_ST'] % implib.bldpath())
	self.link_task.outputs.append(implib)

	if getattr(self, 'defs', None) and self.env.DEST_BINFMT == 'pe':
		node = self.path.find_resource(self.defs)
		if not node:
			raise Errors.WafError('invalid def file %r' % self.defs)
		if 'msvc' in (self.env.CC_NAME, self.env.CXX_NAME):
			self.env.append_value('LINKFLAGS', '/def:%s' % node.abspath())
		else: #gcc for windows takes *.def file a an input without any special flag
			self.link_task.inputs.append(node)

	try:
		inst_to = self.install_path
	except AttributeError:
		inst_to = self.link_task.__class__.inst_to
	if not inst_to:
		return

	self.implib_install_task = self.bld.install_as('${PREFIX}/lib/%s' % implib.name, implib, self.env)

# ============ the code above must not know anything about vnum processing on unix platforms =========

@feature('cshlib', 'cxxshlib', 'dshlib', 'fcshlib', 'vnum')
@after('apply_link')
def apply_vnum(self):
	"""
	libfoo.so is installed as libfoo.so.1.2.3
	create symlinks libfoo.so → libfoo.so.1.2.3 and libfoo.so.1 → libfoo.so.1.2.3
	"""
	if not getattr(self, 'vnum', '') or os.name != 'posix' or self.env.DEST_BINFMT not in ('elf', 'mac-o'):
		return

	link = self.link_task
	nums = self.vnum.split('.')
	node = link.outputs[0]

	libname = node.name
	if libname.endswith('.dylib'):
		name3 = libname.replace('.dylib', '.%s.dylib' % self.vnum)
		name2 = libname.replace('.dylib', '.%s.dylib' % nums[0])
	else:
		name3 = libname + '.' + self.vnum
		name2 = libname + '.' + nums[0]

	# add the so name for the ld linker - to disable, just unset env.SONAME_ST
	if self.env.SONAME_ST:
		v = self.env.SONAME_ST % name2
		self.env.append_value('LINKFLAGS', v.split())

	# the following task is just to enable execution from the build dir :-/
	tsk = self.create_task('vnum', node, [node.parent.find_or_declare(name2), node.parent.find_or_declare(name3)])

	if getattr(self.bld, 'is_install', None):
		self.install_task.hasrun = Task.SKIP_ME
		bld = self.bld
		path = self.install_task.dest
		t1 = bld.install_as(path + os.sep + name3, node, env=self.env)
		t2 = bld.symlink_as(path + os.sep + name2, name3)
		t3 = bld.symlink_as(path + os.sep + libname, name3)
		self.vnum_install_task = (t1, t2, t3)

class vnum_task(Task.Task):
	"""create the symbolic links for a versioned shared library"""
	color = 'CYAN'
	quient = True
	ext_in = ['.bin']
	def run(self):
		for x in self.outputs:
			path = x.abspath()
			try:
				os.remove(path)
			except OSError:
				pass

			try:
				os.symlink(self.inputs[0].name, path)
			except OSError:
				return 1

class fake_shlib(link_task):
	"""task used for reading a foreign library and adding the dependency on it"""
	def runnable_status(self):
		for x in self.outputs:
			x.sig = Utils.h_file(x.abspath())
		return Task.SKIP_ME

class fake_stlib(stlink_task):
	"""task used for reading a foreign library and adding the dependency on it"""
	def runnable_status(self):
		for x in self.outputs:
			x.sig = Utils.h_file(x.abspath())
		return Task.SKIP_ME

@conf
def read_shlib(self, name, paths=[]):
	"""read a foreign shared library for the use system"""
	return self(name=name, features='fake_lib', lib_paths=paths, lib_type='shlib')

@conf
def read_stlib(self, name, paths=[]):
	"""read a foreign static library for the use system"""
	return self(name=name, features='fake_lib', lib_paths=paths, lib_type='stlib')

lib_patterns = {
	'shlib' : ['lib%s.so', '%s.so', 'lib%s.dll', '%s.dll'],
	'stlib' : ['lib%s.a', '%s.a', 'lib%s.dll', '%s.dll', 'lib%s.lib', '%s.lib'],
}

@feature('fake_lib')
def process_lib(self):
	"""
	find the location of a foreign library
	"""
	node = None

	names = [x % self.name for x in lib_patterns[self.lib_type]]
	for x in self.lib_paths + [self.path, '/usr/lib64', '/usr/lib', '/usr/local/lib64', '/usr/local/lib']:
		if not isinstance(x, Node.Node):
			x = self.bld.root.find_node(x) or self.path.find_node(x)
			if not x:
				continue

		for y in names:
			node = x.find_node(y)
			if node:
				node.sig = Utils.h_file(node.abspath())
				break
		else:
			continue
		break
	else:
		raise Errors.WafError('could not find library %r' % self.name)
	self.link_task = self.create_task('fake_%s' % self.lib_type, [], [node])
	self.target = self.name

