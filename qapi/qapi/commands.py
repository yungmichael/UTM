"""
QAPI command marshaller generator

Copyright IBM, Corp. 2011
Copyright (C) 2014-2018 Red Hat, Inc.
Copyright (c) 2019 Halts

Authors:
 Anthony Liguori <aliguori@us.ibm.com>
 Michael Roth <mdroth@linux.vnet.ibm.com>
 Markus Armbruster <armbru@redhat.com>
 Halts <dev@getutm.app>

This work is licensed under the terms of the GNU GPL, version 2.
See the COPYING file in the top-level directory.
"""

from qapi.common import *


def gen_command_decl(name, arg_type, boxed, ret_type, proto=True):
    return mcgen('''
%(c_type)s qmp_%(c_name)s(%(params)s)%(proto)s
''',
                 proto=';' if proto else '', 
                 c_type=(ret_type and ret_type.c_type()) or 'void',
                 c_name=c_name(name),
                 params=build_params(arg_type, boxed, 'Error **errp'))


def gen_marshal_rpc(ret_type):
    return mcgen('''

static %(c_type)s qmp_marshal_rpc_%(c_name)s(CFDictTypeRef args, Error **errp)
{
    Error *err = NULL;
    Visitor *v;
    CFDictTypeRef cfret;
    %(c_type)s ret = {0};

    qmp_rpc_call(args, &cfret, &err);
    if (!err) {
        error_propagate(errp, err);
        return ret;
    }
    v = cf_input_visitor_new(args);
    visit_type_%(c_name)s(v, "return", &ret, &err);
    if (!err) {
        visit_complete(v, ret_out);
    }
    error_propagate(errp, err);
    visit_free(v);
    CFRelease(cfret);
    return ret;
}
''',
                 c_type=ret_type.c_type(), c_name=ret_type.c_name())


def gen_rpc_call(name, arg_type, boxed, ret_type):
    have_args = arg_type and not arg_type.is_empty()

    ret = mcgen('''

%(proto)s
{
    const char *cmdname = "%(name)s";
    CFDictTypeRef cfargs;
    Error *err = NULL;
''',
                name=name, proto=gen_command_decl(name, arg_type, boxed, ret_type, proto=False))

    if ret_type:
        ret += mcgen('''
    %(c_type)s ret;
''',
                     c_type=ret_type.c_type())

    if have_args:
        if boxed:
            visit_type = ('visit_type_%s(v, "arguments", &argp, &err);'
                             % arg_type.c_name())
            ret += mcgen('''
    %(c_name)s *argp = arg;
''',
                     c_name=arg_type.c_name())
        else:
            visit_type = ('visit_type_%s(v, "arguments", &argp, &err);'
                             % arg_type.c_name())
            ret += mcgen('''
    Visitor *v;
    %(c_name)s arg = {
''',
                     c_name=arg_type.c_name())
            if arg_type:
                assert not arg_type.variants
                for memb in arg_type.members:
                    if memb.optional:
                        ret += mcgen('''
        .has_%(c_name)s = has_%(c_name)s,
''',
                                     c_name=c_name(memb.name))
                    ret += mcgen('''
        .%(c_name)s = %(c_name)s,
''',
                                     c_name=c_name(memb.name))
            ret += mcgen('''
    };
    %(c_name)s *argp = &arg;
''',
                                     c_name=arg_type.c_name())
    else:
        visit_type = ''
        ret += mcgen('''
    Visitor *v = NULL;

''')

    ret += mcgen('''
    v = cf_output_visitor_new(&cfargs);
    visit_type_str(v, "execute", (char **)&cmdname, &err);
    if (err) {
        goto out;
    }
    %(visit_type)s
    if (err) {
        goto out;
    }
    visit_complete(v, &cfargs);
''',
                 visit_type=visit_type)

    if ret_type:
        ret += mcgen('''
    ret = qmp_marshal_rpc_%(c_type)s(cfargs, &err);
''',
                    c_type=ret_type.c_name())
    else:
        ret += mcgen('''
    qmp_rpc_call(cfargs, NULL, &err);
''')

    ret += mcgen('''
    CFRelease(cfargs);

out:
    error_propagate(errp, err);
    visit_free(v);
''')

    if ret_type:
        ret += mcgen('''
    return ret;
''')

    ret += mcgen('''
}
''')
    return ret


class QAPISchemaGenCommandVisitor(QAPISchemaModularCVisitor):

    def __init__(self, prefix):
        QAPISchemaModularCVisitor.__init__(
            self, prefix, 'qapi-commands',
            ' * Schema-defined QAPI/QMP commands', __doc__)
        self._visited_ret_types = {}

    def _begin_user_module(self, name):
        self._visited_ret_types[self._genc] = set()
        commands = self._module_basename('qapi-commands', name)
        types = self._module_basename('qapi-types', name)
        visit = self._module_basename('qapi-visit', name)
        self._genc.add(mcgen('''
#include "qemu-compat.h"
#include "cf-output-visitor.h"
#include "cf-input-visitor.h"
#include "dealloc-visitor.h"
#include "error.h"
#include "%(visit)s.h"
#include "%(commands)s.h"

''',
                             commands=commands, visit=visit))
        self._genh.add(mcgen('''
#include "%(types)s.h"

''',
                             types=types))

    def visit_command(self, name, info, ifcond, arg_type, ret_type, gen,
                      success_response, boxed, allow_oob, allow_preconfig):
        if not gen:
            return
        # FIXME: If T is a user-defined type, the user is responsible
        # for making this work, i.e. to make T's condition the
        # conjunction of the T-returning commands' conditions.  If T
        # is a built-in type, this isn't possible: the
        # qmp_marshal_output_T() will be generated unconditionally.
        if ret_type and ret_type not in self._visited_ret_types[self._genc]:
            self._visited_ret_types[self._genc].add(ret_type)
            with ifcontext(ret_type.ifcond,
                           self._genh, self._genc):
                self._genc.add(gen_marshal_rpc(ret_type))
        with ifcontext(ifcond, self._genh, self._genc):
            self._genh.add(gen_command_decl(name, arg_type, boxed, ret_type))
            self._genc.add(gen_rpc_call(name, arg_type, boxed, ret_type))


def gen_commands(schema, output_dir, prefix):
    vis = QAPISchemaGenCommandVisitor(prefix)
    schema.visit(vis)
    vis.write(output_dir)
