#!/usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005-2010 (ita)

"Module called for configuring, compiling and installing targets"

import os, shutil, traceback, datetime, inspect, errno, sys
from waflib import Utils, Configure, Logs, Options, ConfigSet, Context, Errors, Build, Node

build_dir_override = None

no_climb_commands = ['configure']

def waf_entry_point(current_directory, version, wafdir):
	"""This is the main entry point, all Waf execution starts here."""

	Logs.init_log()

	if Context.WAFVERSION != version:
		Logs.error('Waf script %r and library %r do not match (directory %r)' % (version, WAFVERSION, wafdir))
		sys.exit(1)

	Context.waf_dir = wafdir
	Context.launch_dir = current_directory

	# try to find a lock file (if the project was configured)
	# at the same time, store the first wscript file seen
	cur = current_directory
	while cur:
		lst = os.listdir(cur)
		if Options.lockfile in lst:
			env = ConfigSet.ConfigSet()
			try:
				env.load(os.path.join(cur, Options.lockfile))
			except Exception:
				continue

			Context.run_dir = env.run_dir
			Context.top_dir = env.top_dir
			Context.out_dir = env.out_dir

			# the directory of the wscript file was moved
			try:
				os.stat(Context.run_dir)
			except:
				Context.run_dir = cur

			break

		if not Context.run_dir:
			if Context.WSCRIPT_FILE in lst:
				Context.run_dir = cur

		next = os.path.dirname(cur)
		if next == cur:
			break
		cur = next

		# if 'configure' is in the commands, do not search any further
		for k in no_climb_commands:
			if k in sys.argv:
				break
		else:
			continue
		break


	if not Context.run_dir:
		if '-h' in sys.argv or '--help' in sys.argv:
			Logs.warn('No wscript file found: the help message may be incomplete')
			opt_obj = Options.OptionsContext()
			opt_obj.curdir = current_directory
			opt_obj.parse_args()
			sys.exit(0)
		elif '--version' in sys.argv:
			opt_obj = Options.OptionsContext()
			opt_obj.curdir = current_directory
			opt_obj.parse_args()
			sys.exit(0)
		Logs.error('Waf: Run from a directory containing a file named %r' % Context.WSCRIPT_FILE)
		sys.exit(1)

	try:
		os.chdir(Context.run_dir)
	except OSError:
		Logs.error('Waf: The folder %r is unreadable' % Context.run_dir)
		sys.exit(1)

	try:
		set_main_module(Context.run_dir + os.sep + Context.WSCRIPT_FILE)
	except Errors.WafError as e:
		Logs.pprint('RED', e.verbose_msg)
		Logs.error(str(e))
		sys.exit(1)
	except Exception as e:
		Logs.error('Waf: The wscript in %r is unreadable' % Context.run_dir, e)
		traceback.print_exc(file=sys.stdout)
		sys.exit(2)

	parse_options()

	"""
	import cProfile, pstats
	cProfile.runctx("import Scripting; Scripting.run_commands()", {}, {}, 'profi.txt')
	p = pstats.Stats('profi.txt')
	p.sort_stats('time').print_stats(25)
	"""
	try:
		run_commands()
	except Errors.WafError as e:
		if Logs.verbose > 1:
			Logs.pprint('RED', e.verbose_msg)
		Logs.error(e.msg)
		sys.exit(1)
	except Exception as e:
		traceback.print_exc(file=sys.stdout)
		sys.exit(2)
	except KeyboardInterrupt:
		Logs.pprint('RED', 'Interrupted')
		sys.exit(68)
	#"""

def set_main_module(file_path):
	"Read the main wscript file into a module and add missing functions if necessary"
	Context.g_module = Context.load_module(file_path)
	Context.g_module.root_path = file_path

	# note: to register the module globally, use the following:
	# sys.modules['wscript_main'] = g_module

	def set_def(obj):
		name = obj.__name__
		if not name in Context.g_module.__dict__:
			setattr(Context.g_module, name, obj)
	for k in [update, dist, distclean, distcheck]:
		set_def(k)
	# add dummy init and shutdown functions if they're not defined
	if not 'init' in Context.g_module.__dict__:
		Context.g_module.init = Utils.nada
	if not 'shutdown' in Context.g_module.__dict__:
		Context.g_module.shutdown = Utils.nada
	if not 'options' in Context.g_module.__dict__:
		Context.g_module.options = Utils.nada

def parse_options():
	"""parse the command-line options and initialize the logging system"""
	opt = Options.OptionsContext().execute()

	if not Options.commands:
		Options.commands = ['build']

	# process some internal Waf options
	Logs.verbose = Options.options.verbose
	Logs.init_log()

	if Options.options.zones:
		Logs.zones = Options.options.zones.split(',')
		if not Logs.verbose:
			Logs.verbose = 1
	elif Logs.verbose > 0:
		Logs.zones = ['runner']

	if Logs.verbose > 2:
		Logs.zones = ['*']

def run_command(cmd_name):
	"""run a single command (usually given on the command line)"""
	ctx = Context.create_context(cmd_name)
	ctx.options = Options.options # provided for convenience
	ctx.cmd = cmd_name
	ctx.execute()
	return ctx

def run_commands():
	"""execute the commands that were given on the command-line, depends on parse_options"""
	run_command('init')
	while Options.commands:
		cmd_name = Options.commands.pop(0)

		timer = Utils.Timer()
		run_command(cmd_name)
		if not Options.options.progress_bar:
			elapsed = ' (%s)' % str(timer)
			Logs.info('%r finished successfully%s' % (cmd_name, elapsed))
	run_command('shutdown')

###########################################################################################

def _can_distclean(name):
	"""
	WARNING: this method may disappear anytime
	"""
	for k in '.o .moc .exe'.split():
		if name.endswith(k):
			return True
	return False

def distclean_dir(dirname):
	"""
	called when top==out
	"""
	for (root, dirs, files) in os.walk(dirname):
		for f in files:
			if _can_distclean(f):
				fname = root + os.sep + f
				try:
					os.unlink(fname)
				except:
					Logs.warn('could not remove %r' % fname)

	for x in [DBFILE, 'config.log']:
		try:
			os.unlink(x)
		except:
			pass

	try:
		shutil.rmtree('c4che')
	except:
		pass

def distclean(ctx):
	'''removes the build directory'''
	lst = os.listdir('.')
	for f in lst:
		if f == Options.lockfile:
			try:
				proj = ConfigSet.ConfigSet(f)
			except:
				Logs.warn('could not read %r' % f)
				continue

			if proj['out_dir'] != proj['top_dir']:
				try:
					shutil.rmtree(proj['out_dir'])
				except IOError:
					pass
				except OSError as e:
					if e.errno != errno.ENOENT:
						Logs.warn('project %r cannot be removed' % proj[Context.OUT])
			else:
				distclean_dir(proj['out_dir'])

			for k in (proj['out_dir'], proj['top_dir'], proj['run_dir']):
				try:
					os.remove(os.path.join(k, Options.lockfile))
				except OSError as e:
					if e.errno != errno.ENOENT:
						Logs.warn('file %r cannot be removed' % f)

		# remove the local waf cache
		if f.startswith('.waf-') and not Options.commands:
			shutil.rmtree(f, ignore_errors=True)

class Dist(Context.Context):
	"""
	Create an archive containing the source code on 'waf dist'
	"""
	cmd = 'dist'
	fun = 'dist'
	algo = 'tar.bz2'
	ext_algo = {}

	def execute(self):
		"See waflib.Context.Context.execute"
		self.recurse([os.path.dirname(Context.g_module.root_path)])
		self.archive()

	def archive(self):
		"""
		Create the archive (override or subclass)
		"""
		import tarfile

		arch_name = self.get_arch_name()

		try:
			self.base_path
		except:
			self.base_path = self.path

		node = self.base_path.make_node(arch_name)
		try:
			node.delete()
		except:
			pass

		files = self.get_files()

		if self.algo.startswith('tar.'):
			tar = tarfile.open(arch_name, 'w:' + self.algo.replace('tar.', ''))

			for x in files:
				tinfo = tar.gettarinfo(name=x.abspath(), arcname=self.get_base_name() + '/' + x.path_from(self.base_path))
				tinfo.uid   = 0
				tinfo.gid   = 0
				tinfo.uname = 'root'
				tinfo.gname = 'root'

				fu = None
				try:
					fu = open(x.abspath())
					tar.addfile(tinfo, fileobj=fu)
				finally:
					fu.close()

			tar.close()
		elif self.algo == 'zip':
			import zipfile
			zip = zipfile.ZipFile(arch_name, 'w', compression=zipfile.ZIP_DEFLATED)

			for x in files:
				archive_name = self.get_base_name() + '/' + x.path_from(self.base_path)
				zip.write(x.abspath(), archive_name, zipfile.ZIP_DEFLATED)
			zip.close()
		else:
			self.fatal('Valid algo types are tar.bz2, tar.gz or zip')

		try:
			from hashlib import sha1 as sha
		except ImportError:
			from sha import sha
		try:
			digest = " (sha=%r)" % sha(node.read()).hexdigest()
		except:
			digest = ''

		Logs.info('New archive created: %s%s' % (self.arch_name, digest))

	def get_arch_name(self):
		"""
		return the name of the archive to create
		if it does not work, set "self.arch_name"
		"""
		try:
			self.arch_name
		except:
			self.arch_name = self.get_base_name() + '.' + self.ext_algo.get(self.algo, self.algo)
		return self.arch_name

	def get_base_name(self):
		"""
		name of the directory in the archive
		"""
		try:
			self.base_name
		except:
			appname = getattr(Context.g_module, Context.APPNAME, 'noname')
			version = getattr(Context.g_module, Context.VERSION, '1.0')
			self.base_name = appname + '-' + version
		return self.base_name

	def get_excl(self):
		"""
		return the patterns to exclude, which is important for the build directory
		if it does not work, set "self.excl"
		"""
		try:
			return self.excl
		except:
			self.excl = Node.exclude_regs + ' **/waf-1.6.* **/.waf-1.6* **/*~ **/*.rej **/*.orig **/*.pyc **/*.pyo **/*.bak **/*.swp **/.lock-w*'
			nd = self.root.find_node(Context.out_dir)
			if nd:
				self.excl += ' ' + nd.path_from(self.base_path)
			return self.excl

	def get_files(self):
		"""
		return the list of nodes representing the files to include
		if it is not satisfactory, set "self.files"
		"""
		try:
			files = self.files
		except:
			files = self.base_path.ant_glob('**/*', excl=self.get_excl())
		return files


def dist(ctx):
	'''makes a tarball for redistributing the sources'''
	pass

class DistCheck(Dist):
	"""
	create an archive with 'waf dist', then try to build it in a temporary directory
	this is less useful with waf, as all files are included by default (vs excluded for autotools)
	"""

	fun = 'distcheck'
	cmd = 'distcheck'

	def execute(self):
		"See waflib.Context.Context.execute"
		self.recurse([os.path.dirname(Context.g_module.root_path)])
		self.archive()
		self.check()

	def check(self):
		"""create the archive, uncompress it and try to build the project"""
		import tempfile, tarfile

		t = None
		try:
			t = tarfile.open(self.get_arch_name())
			for x in t:
				t.extract(x)
		finally:
			if t:
				t.close()

		instdir = tempfile.mkdtemp('.inst', self.get_base_name())
		ret = Utils.subprocess.Popen([sys.argv[0], 'configure', 'install', 'uninstall', '--destdir=' + instdir], cwd=self.get_base_name()).wait()
		if ret:
			raise Errors.WafError('distcheck failed with code %i' % ret)

		if os.path.exists(instdir):
			raise Errors.WafError('distcheck succeeded, but files were left in %s' % instdir)

		shutil.rmtree(self.get_base_name())


def distcheck(ctx):
	'''checks if the project compiles (tarball from 'dist')'''
	pass

def update(ctx):
	"""download a specific tool into the local waf directory"""
	lst = os.listdir(Context.waf_dir + '/waflib/extras')
	for x in lst:
		if not x.endswith('.py'):
			continue
		tool = x.replace('.py', '')
		Configure.download_tool(tool, force=True)

def autoconfigure(execute_method):
	"""decorator used to set the commands that can be configured automatically"""
	def execute(self):
		if not Configure.autoconfig:
			return execute_method(self)

		env = ConfigSet.ConfigSet()
		do_config = False
		try:
			env.load(os.path.join(Context.top_dir, Options.lockfile))
		except Exception as e:
			Logs.warn('Configuring the project')
			do_config = True
		else:
			h = 0
			for f in env['files']:
				h = hash((h, Utils.readf(f, 'rb')))
			do_config = h != env.hash

		if do_config:
			Options.commands.insert(0, self.cmd)
			Options.commands.insert(0, 'configure')
			return

		return execute_method(self)
	return execute
Build.BuildContext.execute = autoconfigure(Build.BuildContext.execute)

