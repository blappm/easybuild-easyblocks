##
# Copyright 2012 Toon Willems
# Copyright 2012 Kenneth Hoste
#
# This file is part of EasyBuild,
# originally created by the HPC team of the University of Ghent (http://ugent.be/hpc).
#
# http://github.com/hpcugent/easybuild
#
# EasyBuild is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation v2.
#
# EasyBuild is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
##
import os
import re
import shutil
import tempfile

import easybuild.framework.easyconfig as easyconfig
from unittest import TestCase, TestSuite
from easybuild.framework.easyconfig import EasyConfig, tweak, obtain_ec_for
from easybuild.tools.build_log import EasyBuildError, initLogger
from easybuild.tools.systemtools import get_shared_lib_ext

log_fn = "/tmp/easybuild_easyconfig_tests.log"
_, log, logh = initLogger(filename=log_fn, debug=True, typ="easybuild_easyconfig_test")

class EasyConfigTest(TestCase):
    """ Baseclass for easyblock testcases """

    def setUp(self):
        """ create temporary easyconfig file """
        self.eb_file = "/tmp/easyconfig_test_file.eb"
        f = open(self.eb_file, "w")
        f.write(self.contents)
        f.close()

    def tearDown(self):
        """ make sure to remove the temporary file """
        os.remove(self.eb_file)

    def assertErrorRegex(self, error, regex, call, *args):
        """ convenience method to match regex with the error message """
        try:
            call(*args)
            self.assertTrue(False)  # this will fail when no exception is thrown at all
        except error, err:
            res = re.search(regex, err.msg)
            if not res:
                print "err: %s" % err
            self.assertTrue(res)


class TestEmpty(EasyConfigTest):
    """ Test empty easyblocks """

    contents = "# empty string"

    def runTest(self):
        """ empty files should not parse! """
        self.assertRaises(EasyBuildError, EasyConfig, self.eb_file)
        self.assertErrorRegex(EasyBuildError, "expected a valid path", EasyConfig, "")


class TestMandatory(EasyConfigTest):
    """ Test mandatory variable validation """

    contents = """
name = "pi"
version = "3.14"
"""

    def runTest(self):
        """ make sure all checking of mandatory variables works """
        self.assertErrorRegex(EasyBuildError, "mandatory variables .* not provided", EasyConfig, self.eb_file)

        self.contents += "\n".join(['homepage = "http://google.com"', 'description = "test easyconfig"',
                                    'toolkit = {"name": "dummy", "version": "dummy"}'])
        self.setUp()

        eb = EasyConfig(self.eb_file)

        self.assertEqual(eb['name'], "pi")
        self.assertEqual(eb['version'], "3.14")
        self.assertEqual(eb['homepage'], "http://google.com")
        self.assertEqual(eb['toolkit'], {"name":"dummy", "version": "dummy"})
        self.assertEqual(eb['description'], "test easyconfig")


class TestValidation(EasyConfigTest):
    """ test other validations """

    contents = """
name = "pi"
version = "3.14"
homepage = "http://google.com"
description = "test easyconfig"
toolkit = {"name":"dummy", "version": "dummy"}
stop = 'notvalid'
"""

    def runTest(self):
        """ test other validations beside mandatory variables """
        eb = EasyConfig(self.eb_file, validate=False)
        self.assertErrorRegex(EasyBuildError, "\w* provided \w* is not valid", eb.validate)

        eb['stop'] = 'patch'
        # this should now not crash
        eb.validate()

        eb['osdependencies'] = ['non-existent-dep']
        self.assertErrorRegex(EasyBuildError, "OS dependencies were not found", eb.validate)

        # dummy toolkit, installversion == version
        self.assertEqual(eb.installversion(), "3.14")

        os.chmod(self.eb_file, 0000)
        self.assertErrorRegex(EasyBuildError, "Unexpected IOError", EasyConfig, self.eb_file)
        os.chmod(self.eb_file, 0755)

        self.contents += "\nsyntax_error'"
        self.setUp()
        self.assertErrorRegex(EasyBuildError, "SyntaxError", EasyConfig, self.eb_file)


class TestSharedLibExt(EasyConfigTest):
    """ test availability of shared_lib_ext in easyblock context """

    contents = """
name = "pi"
version = "3.14"
homepage = "http://google.com"
description = "test easyconfig"
toolkit = {"name":"dummy", "version": "dummy"}
sanityCheckPaths = { 'files': ["lib/lib.%s" % shared_lib_ext] }
"""

    def runTest(self):
        """ inside easyconfigs shared_lib_ext should be set """
        eb = EasyConfig(self.eb_file)
        self.assertEqual(eb['sanityCheckPaths']['files'][0], "lib/lib.%s" % get_shared_lib_ext())


class TestDependency(EasyConfigTest):
    """ Test parsing of dependencies """

    contents = """
name = "pi"
version = "3.14"
homepage = "http://google.com"
description = "test easyconfig"
toolkit = {"name":"GCC", "version": "4.6.3"}
dependencies = [('first', '1.1'), {'name': 'second', 'version': '2.2'}]
builddependencies = [('first', '1.1'), {'name': 'second', 'version': '2.2'}]
"""

    def runTest(self):
        """ test all possible ways of specifying dependencies """
        eb = EasyConfig(self.eb_file)
        # should include builddependencies
        self.assertEqual(len(eb.dependencies()), 4)
        self.assertEqual(len(eb.builddependencies()), 2)

        first = eb.dependencies()[0]
        second = eb.dependencies()[1]

        self.assertEqual(first['name'], "first")
        self.assertEqual(second['name'], "second")

        self.assertEqual(first['version'], "1.1")
        self.assertEqual(second['version'], "2.2")

        self.assertEqual(first['tk'], '1.1-GCC-4.6.3')
        self.assertEqual(second['tk'], '2.2-GCC-4.6.3')

        # same tests for builddependencies
        first = eb.builddependencies()[0]
        second = eb.builddependencies()[1]

        self.assertEqual(first['name'], "first")
        self.assertEqual(second['name'], "second")

        self.assertEqual(first['version'], "1.1")
        self.assertEqual(second['version'], "2.2")

        self.assertEqual(first['tk'], '1.1-GCC-4.6.3')
        self.assertEqual(second['tk'], '2.2-GCC-4.6.3')

        eb['dependencies'] = ["wrong type"]
        self.assertErrorRegex(EasyBuildError, "wrong type from unsupported type", eb.dependencies)

        eb['dependencies'] = [()]
        self.assertErrorRegex(EasyBuildError, "without name", eb.dependencies)
        eb['dependencies'] = [{'name': "test"}]
        self.assertErrorRegex(EasyBuildError, "without version", eb.dependencies)


class TestExtraOptions(EasyConfigTest):
    """ test extra options constructor """

    contents = """
name = "pi"
version = "3.14"
homepage = "http://google.com"
description = "test easyconfig"
toolkit = {"name":"GCC", "version": "4.6.3"}
toolkitopts = { "static": True}
dependencies = [('first', '1.1'), {'name': 'second', 'version': '2.2'}]
"""

    def runTest(self):
        """ extra_options should allow other variables to be stored """
        eb = EasyConfig(self.eb_file)
        self.assertRaises(KeyError, lambda: eb['custom_key'])

        extra_vars = [('custom_key', ['default', "This is a default key", easyconfig.CUSTOM])]

        eb = EasyConfig(self.eb_file, extra_vars)
        self.assertEqual(eb['custom_key'], 'default')

        eb['custom_key'] = "not so default"
        self.assertEqual(eb['custom_key'], 'not so default')

        self.contents += "\ncustom_key = 'test'"

        self.setUp()

        eb = EasyConfig(self.eb_file, extra_vars)
        self.assertEqual(eb['custom_key'], 'test')

        eb['custom_key'] = "not so default"
        self.assertEqual(eb['custom_key'], 'not so default')

        # test if extra toolkit options are being passed
        self.assertEqual(eb.toolkit().opts['static'], True)

        extra_vars.extend([('mandatory_key', ['default', 'another mandatory key', easyconfig.MANDATORY])])

        # test extra mandatory vars
        self.assertErrorRegex(EasyBuildError, "mandatory variables \S* not provided", EasyConfig, self.eb_file, extra_vars)

        self.contents += '\nmandatory_key = "value"'
        self.setUp()

        eb = EasyConfig(self.eb_file, extra_vars)

        self.assertEqual(eb['mandatory_key'], 'value')


class TestSuggestions(EasyConfigTest):
    """ test suggestions on typos """

    contents = """
name = "pi"
version = "3.14"
homepage = "http://google.com"
description = "test easyconfig"
toolkit = {"name":"GCC", "version": "4.6.3"}
dependencis = [('first', '1.1'), {'name': 'second', 'version': '2.2'}]
sourceULs = ['http://google.com']
"""

    def runTest(self):
        """ If a typo is present, suggestion should be provided (if possible) """
        self.assertErrorRegex(EasyBuildError, "dependencis -> dependencies", EasyConfig, self.eb_file)
        self.assertErrorRegex(EasyBuildError, "sourceULs -> sourceURLs", EasyConfig, self.eb_file)


class TestTweaking(EasyConfigTest):
    """test tweaking ability of easyconfigs"""

    tweaked_fn = "/tmp/tweaked.eb"

    patches = ["t1.patch", ("t2.patch", 1), ("t3.patch", "test"), ("t4.h", "include")]
    contents = """
name = "pi"
homepage = "http://www.google.com"
description = "dummy description"
version = "3.14"
toolkit = {"name":"GCC", "version": "4.6.3"}
patches = %s
""" % str(patches)

    def runTest(self):

        ver = "1.2.3"
        verpref = "myprefix"
        versuff = "mysuffix"
        tkname = "mytk"
        tkver = "4.1.2"
        extra_patches = ['t5.patch', 't6.patch']
        homepage = "http://www.justatest.com"

        tweaks = {
                  'version': ver,
                  'versionprefix': verpref,
                  'versionsuffix': versuff,
                  'toolkit_version': tkver,
                  'patches': extra_patches
                 }
        tweak(self.eb_file, self.tweaked_fn, tweaks, log)

        eb = EasyConfig(self.tweaked_fn)
        self.assertEqual(eb['version'], ver)
        self.assertEqual(eb['versionprefix'], verpref)
        self.assertEqual(eb['versionsuffix'], versuff)
        self.assertEqual(eb['toolkit']['version'], tkver)
        self.assertEqual(eb['patches'], extra_patches + self.patches)

        eb = EasyConfig(self.eb_file)
        eb['version'] = ver
        eb['toolkit']['version'] = tkver
        eb.dump(self.eb_file)

        tweaks = {
                  'toolkit_name': tkname,
                  'patches': extra_patches[0:1],
                  'homepage': homepage,
                  'foo': "bar"
                 }

        tweak(self.eb_file, self.tweaked_fn, tweaks, log)

        eb = EasyConfig(self.tweaked_fn)
        self.assertEqual(eb['toolkit']['name'], tkname)
        self.assertEqual(eb['toolkit']['version'], tkver)
        self.assertEqual(eb['patches'], extra_patches[0:1] + self.patches)
        self.assertEqual(eb['version'], ver)
        self.assertEqual(eb['homepage'], homepage)

    def tearDown(self):
        EasyConfigTest.tearDown(self)
        os.remove(self.tweaked_fn)

class TestInstallVersion(EasyConfigTest):
    """test generation of install version"""

    contents = ""

    def runTest(self):

        ver = "3.14"
        verpref = "myprefix|"
        versuff = "|mysuffix"
        tkname = "GCC"
        tkver = "4.6.3"
        dummy = "dummy"

        installver = easyconfig.det_installversion(ver, tkname, tkver, verpref, versuff)

        self.assertEqual(installver, "%s%s-%s-%s%s" % (verpref, ver, tkname, tkver, versuff))

        installver = easyconfig.det_installversion(ver, dummy, tkver, verpref, versuff)

        self.assertEqual(installver, "%s%s%s" % (verpref, ver, versuff))

class TestObtainEasyconfig(EasyConfigTest):
    """test obtain an easyconfig file given certain specifications"""

    contents = ""

    def runTest(self):

        tkname = 'GCC'
        tkver = '4.3.2'
        patches = ["one.patch"]

        # prepare a couple of eb files to test again
        fns = ["pi-3.14.eb",
               "pi-3.13-GCC-4.3.2.eb",
               "pi-3.15-GCC-4.3.2.eb",
               "pi-3.15-GCC-4.4.5.eb",
               "foo-1.2.3-GCC-4.3.2.eb"]
        eb_files = [(fns[0], "\n".join(['name = "pi"',
                                        'version = "3.12"',
                                        'homepage = "http://example.com"',
                                        'description = "test easyconfig"',
                                        'toolkit = {"name": "dummy", "version": "dummy"}',
                                        'patches = %s' % patches
                                        ])),
                    (fns[1], "\n".join(['name = "pi"',
                                        'version = "3.13"',
                                        'homepage = "http://google.com"',
                                        'description = "test easyconfig"',
                                        'toolkit = {"name": "%s", "version": "%s"}' % (tkname, tkver),
                                        'patches = %s' % patches
                                       ])),
                    (fns[2], "\n".join(['name = "pi"',
                                        'version = "3.15"',
                                        'homepage = "http://google.com"',
                                        'description = "test easyconfig"',
                                        'toolkit = {"name": "%s", "version": "%s"}' % (tkname, tkver),
                                        'patches = %s' % patches
                                       ])),
                    (fns[3], "\n".join(['name = "pi"',
                                        'version = "3.15"',
                                        'homepage = "http://google.com"',
                                        'description = "test easyconfig"',
                                        'toolkit = {"name": "%s", "version": "4.5.1"}' % tkname,
                                        'patches = %s' % patches
                                       ])),
                    (fns[4], "\n".join(['name = "foo"',
                                        'version = "1.2.3"',
                                        'homepage = "http://example.com"',
                                        'description = "test easyconfig"',
                                        'toolkit = {"name": "%s", "version": "%s"}' % (tkname, tkver)
                                       ]))
                   ]


        self.ec_dir = tempfile.mkdtemp()

        for (fn, txt) in eb_files:
            f = open(os.path.join(self.ec_dir, fn), "w")
            f.write(txt)
            f.close()

        # should crash when no suited easyconfig file (or template) is available
        specs = {'name': 'nosuchsoftware'}
        error_regexp = ".*No easyconfig files found for software %s, and no templates available. I'm all out of ideas." % specs['name']
        self.assertErrorRegex(EasyBuildError, error_regexp, obtain_ec_for, specs, self.ec_dir, None, log)

        # should find matching easyconfig file
        specs = {'name': 'foo', 'version': '1.2.3'}
        res = obtain_ec_for(specs, self.ec_dir, None, log)
        self.assertEqual(res, os.path.join(self.ec_dir, fns[-1]))

        # should not pick between multiple available toolkit names
        name = "pi"
        ver = "3.12"
        suff = "mysuff"
        specs.update({
                      'name': name,
                      'version': ver,
                      'versionsuffix': suff
                     })
        error_regexp = ".*No toolkit name specified, and more than one available: .*"
        self.assertErrorRegex(EasyBuildError, error_regexp, obtain_ec_for, specs, self.ec_dir, None, log)

        # should be able to generate an easyconfig file that slightly differs
        ver = '3.16'
        specs.update({
                      'toolkit_name': tkname,
                      'toolkit_version': tkver,
                      'version': ver,
                      'foo': 'bar123'
                     })
        res = obtain_ec_for(specs, self.ec_dir, None, log)
        self.assertEqual(res, "%s-%s-%s-%s%s.eb" % (name, ver, tkname, tkver, suff))

        ec = EasyConfig(res)
        self.assertEqual(ec['name'], specs['name'])
        self.assertEqual(ec['version'], specs['version'])
        self.assertEqual(ec['versionsuffix'], specs['versionsuffix'])
        self.assertEqual(ec['toolkit'], {'name': tkname, 'version': tkver})
        # can't check for key 'foo', because EasyConfig ignores parameter names it doesn't know about
        txt = open(res, "r").read()
        self.assertTrue(re.search("foo = '%s'" % specs['foo'], txt))
        os.remove(res)

        # should pick correct version, i.e. not newer than what's specified, if a choice needs to be made
        ver = '3.14'
        specs.update({'version': ver})
        res = obtain_ec_for(specs, self.ec_dir, None, log)
        ec = EasyConfig(res)
        self.assertEqual(ec['version'], specs['version'])
        txt = open(res, "r").read()
        self.assertTrue(re.search("version = [\"']%s[\"'] .*was: [\"']3.13[\"']" % ver, txt))
        os.remove(res)

        # should pick correct toolkit version as well, i.e. now newer than what's specified, if a choice needs to be made
        specs.update({
                      'version': '3.15',
                      'toolkit_version': '4.4.5',
                     })
        res = obtain_ec_for(specs, self.ec_dir, None, log)
        ec = EasyConfig(res)
        self.assertEqual(ec['version'], specs['version'])
        self.assertEqual(ec['toolkit']['version'], specs['toolkit_version'])
        txt = open(res, "r").read()
        pattern = "toolkit = .*version.*[\"']%s[\"'].*was: .*version.*[\"']%s[\"']" % (specs['toolkit_version'], tkver)
        self.assertTrue(re.search(pattern, txt))
        os.remove(res)


        # should be able to prepend to list of patches and handle list of dependencies
        extra_patches = ['two.patch', 'three.patch']
        deps = [('foo', '1.2.3'), ('bar', '666')]
        specs.update({
                      'patches': extra_patches,
                      'dependencies': deps
                     })
        res = obtain_ec_for(specs, self.ec_dir, None, log)
        ec = EasyConfig(res)
        self.assertEqual(ec['patches'], specs['patches'] + patches)
        self.assertEqual(ec['dependencies'], specs['dependencies'])
        os.remove(res)

        # should use supplied filename
        fn = "my.eb"
        res = obtain_ec_for(specs, self.ec_dir, fn, log)
        self.assertEqual(res, fn)
        os.remove(res)

        # should use a template if it's there
        shutil.copy2(os.path.join("easybuild", "easyconfigs", "TEMPLATE.eb"), self.ec_dir)
        specs.update({'name': 'nosuchsoftware'})
        res = obtain_ec_for(specs, self.ec_dir, None, log)
        ec = EasyConfig(res)
        self.assertEqual(ec['name'], specs['name'])
        os.remove(res)

    def tearDown(self):
        """Cleanup: remove temp dir with test easyconfig files."""
        EasyConfigTest.tearDown(self)
        shutil.rmtree(self.ec_dir)

def suite():
    """ return all the tests in this file """
    return TestSuite([TestDependency(), TestEmpty(), TestExtraOptions(),
                      TestMandatory(), TestSharedLibExt(), TestSuggestions(),
                      TestValidation(), TestTweaking(), TestInstallVersion(),
                      TestObtainEasyconfig()])
