#! /usr/bin/env python
# encoding: utf-8
# WARNING! All changes made to this file will be lost!

import sys
if sys.hexversion < 0x020400f0: from sets import Set as set
import os,re
from waflib.Configure import conf
from waflib import TaskGen,Task,Utils,Options,Build
from waflib.TaskGen import feature,before,after
SOURCE_RE='**/*.java'
JAR_RE='**/*'
class_check_source='''
public class Test {
	public static void main(String[] argv) {
		Class lib;
		if (argv.length < 1) {
			System.err.println("Missing argument");
			System.exit(77);
		}
		try {
			lib = Class.forName(argv[0]);
		} catch (ClassNotFoundException e) {
			System.err.println("ClassNotFoundException");
			System.exit(1);
		}
		lib = null;
		System.exit(0);
	}
}
'''
def apply_java(self):
	Utils.def_attrs(self,jarname='',classpath='',sourcepath='.',srcdir='.',jar_mf_attributes={},jar_mf_classpath=[])
	nodes_lst=[]
	if not self.classpath:
		if not self.env['CLASSPATH']:
			self.env['CLASSPATH']='..'+os.pathsep+'.'
	else:
		self.env['CLASSPATH']=self.classpath
	if isinstance(self.srcdir,self.path.__class__):
		srcdir_node=self.srcdir
	else:
		srcdir_node=self.path.find_dir(self.srcdir)
	if not srcdir_node:
		raise Errors.WafError('could not find srcdir %r'%self.srcdir)
	self.env['OUTDIR']=[srcdir_node.get_src().srcpath()]
	self.javac_task=tsk=self.create_task('javac')
	tsk.srcdir=srcdir_node
	if getattr(self,'compat',None):
		tsk.env.append_value('JAVACFLAGS',['-source',self.compat])
	if hasattr(self,'sourcepath'):
		fold=[isinstance(x,self.path.__class__)and x or self.path.find_dir(x)for x in self.to_list(self.sourcepath)]
		names=os.pathsep.join([x.srcpath()for x in fold])
	else:
		names=srcdir_node.srcpath()
	if names:
		tsk.env.append_value('JAVACFLAGS',['-sourcepath',names])
def use_javac_files(self):
	lst=[]
	names=self.to_list(getattr(self,'use',[]))
	get=self.bld.get_tgen_by_name
	for x in names:
		y=get(x)
		y.post()
		lst.append(y.jar_task.outputs[0].abspath())
		self.javac_task.set_run_after(y.jar_task)
	if lst:
		self.env['CLASSPATH']=(self.env.CLASSPATH or'')+os.pathsep+os.pathsep.join(lst)+os.pathsep
def jar_files(self):
	basedir=getattr(self,'basedir','.')
	destfile=getattr(self,'destfile','test.jar')
	jaropts=getattr(self,'jaropts',[])
	jarcreate=getattr(self,'jarcreate','cf')
	if isinstance(self.basedir,self.path.__class__):
		srcdir_node=self.basedir
	else:
		srcdir_node=self.path.find_dir(self.basedir)
	if not srcdir_node:
		raise Errors.WafError('could not find basedir %r'%self.srcdir)
	self.jar_task=tsk=self.create_task('jar_create')
	tsk.set_outputs(self.path.find_or_declare(destfile))
	tsk.basedir=srcdir_node
	jaropts.append('-C')
	jaropts.append(srcdir_node.get_bld().bldpath())
	jaropts.append('.')
	tsk.env['JAROPTS']=jaropts
	tsk.env['JARCREATE']=jarcreate
	if getattr(self,'javac_task',None):
		tsk.set_run_after(self.javac_task)
def use_jar_files(self):
	lst=[]
	names=self.to_list(getattr(self,'use',[]))
	get=self.bld.get_tgen_by_name
	for x in names:
		y=get(x)
		y.post()
		self.jar_task.run_after.update(y.tasks)
class jar_create(Task.Task):
	color='GREEN'
	run_str='${JAR} ${JARCREATE} ${TGT} ${JAROPTS}'
	def runnable_status(self):
		for t in self.run_after:
			if not t.hasrun:
				return Task.ASK_LATER
		if not self.inputs:
			global JAR_RE
			self.inputs=[x for x in self.basedir.get_bld().ant_glob(JAR_RE,dir=False)if id(x)!=id(self.outputs[0])]
		return super(jar_create,self).runnable_status()
class javac(Task.Task):
	color='BLUE'
	run_str='${JAVAC} -classpath ${CLASSPATH} -d ${OUTDIR} ${JAVACFLAGS} ${SRC}'
	def runnable_status(self):
		for t in self.run_after:
			if not t.hasrun:
				return Task.ASK_LATER
		if not self.inputs:
			global SOURCE_RE
			self.inputs=self.srcdir.ant_glob(SOURCE_RE)
		if not self.outputs:
			self.outputs=[x.change_ext('.class')for x in self.inputs if x.name!='package-info.java']
		return super(javac,self).runnable_status()
	def post_run(self):
		lst=set([x.parent for x in self.outputs])
		inner=[]
		for k in lst:
			lst=k.listdir()
			for u in lst:
				if u.find('$')>=0:
					node=k.find_or_declare(u)
					inner.append(node)
		to_add=set(inner)-set(self.outputs)
		self.outputs.extend(list(to_add))
		self.cached=True
		return super(javac,self).post_run()
def configure(self):
	java_path=self.environ['PATH'].split(os.pathsep)
	v=self.env
	if'JAVA_HOME'in self.environ:
		java_path=[os.path.join(self.environ['JAVA_HOME'],'bin')]+java_path
		self.env['JAVA_HOME']=[self.environ['JAVA_HOME']]
	for x in'javac java jar'.split():
		self.find_program(x,var=x.upper(),path_list=java_path)
		self.env[x.upper()]=self.cmd_to_list(self.env[x.upper()])
	if'CLASSPATH'in self.environ:
		v['CLASSPATH']=self.environ['CLASSPATH']
	if not v['JAR']:self.fatal('jar is required for making java packages')
	if not v['JAVAC']:self.fatal('javac is required for compiling java classes')
	v['JARCREATE']='cf'
def check_java_class(self,classname,with_classpath=None):
	import shutil
	javatestdir='.waf-javatest'
	classpath=javatestdir
	if self.env['CLASSPATH']:
		classpath+=os.pathsep+self.env['CLASSPATH']
	if isinstance(with_classpath,str):
		classpath+=os.pathsep+with_classpath
	shutil.rmtree(javatestdir,True)
	os.mkdir(javatestdir)
	java_file=open(os.path.join(javatestdir,'Test.java'),'w')
	java_file.write(class_check_source)
	java_file.close()
	self.exec_command(self.env['JAVAC']+[os.path.join(javatestdir,'Test.java')],shell=False)
	cmd=self.env['JAVA']+['-cp',classpath,'Test',classname]
	self.to_log("%s\n"%str(cmd))
	found=self.exec_command(cmd,shell=False)
	self.msg('Checking for java class %s'%classname,not found)
	shutil.rmtree(javatestdir,True)
	return found
def check_jni_headers(conf):
	if not conf.env.CC_NAME and not conf.env.CXX_NAME:
		conf.fatal('load a compiler first (gcc, g++, ..)')
	if not conf.env.JAVA_HOME:
		conf.fatal('set JAVA_HOME in the system environment')
	javaHome=conf.env['JAVA_HOME'][0]
	dir=conf.root.find_dir(conf.env.JAVA_HOME[0]+'/include')
	f=dir.ant_glob('**/(jni|jni_md).h')
	incDirs=[x.parent.abspath()for x in f]
	dir=conf.root.find_dir(conf.env.JAVA_HOME[0])
	f=dir.ant_glob('**/*jvm.(so|dll)')
	libDirs=[x.parent.abspath()for x in f]or[javaHome]
	for i,d in enumerate(libDirs):
		if conf.check(header_name='jni.h',define_name='HAVE_JNI_H',lib='jvm',libpath=d,includes=incDirs,uselib_store='JAVA',uselib='JAVA'):
			break
	else:
		conf.fatal('could not find lib jvm in %r (see config.log)'%libDirs)

feature('javac')(apply_java)
before('process_source')(apply_java)
feature('javac')(use_javac_files)
after('apply_java')(use_javac_files)
feature('jar')(jar_files)
after('apply_java','use_javac_files')(jar_files)
before('process_source')(jar_files)
feature('jar')(use_jar_files)
after('jar_files')(use_jar_files)
conf(check_java_class)
conf(check_jni_headers)