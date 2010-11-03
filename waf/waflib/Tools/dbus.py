#!/usr/bin/env python
# encoding: utf-8
# Ali Sabil, 2007

from waflib import Task
from waflib.TaskGen import taskgen_method, before

@taskgen_method
def add_dbus_file(self, filename, prefix, mode):
	if not hasattr(self, 'dbus_lst'):
		self.dbus_lst = []
	if not 'process_dbus' in self.meths:
		self.meths.append('process_dbus')
	self.dbus_lst.append([filename, prefix, mode])

@before('apply_core')
def process_dbus(self):
	for filename, prefix, mode in getattr(self, 'dbus_lst', []):
		node = self.path.find_resource(filename)

		if not node:
			raise Errors.WafError('file not found ' + filename)

		tsk = self.create_task('dbus_binding_tool', node, node.change_ext('.h'))

		tsk.env.DBUS_BINDING_TOOL_PREFIX = prefix
		tsk.env.DBUS_BINDING_TOOL_MODE   = mode

class dbus_binding_tool(Task.Task):
	color   = 'BLUE'
	ext_out = ['.h']
	run_str = '${DBUS_BINDING_TOOL} --prefix=${DBUS_BINDING_TOOL_PREFIX} --mode=${DBUS_BINDING_TOOL_MODE} --output=${TGT} ${SRC}'

def configure(conf):
	dbus_binding_tool = conf.find_program('dbus-binding-tool', var='DBUS_BINDING_TOOL')

