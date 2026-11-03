#!/usr/bin/env python3
"""Install the task-owned Windows package before testing its native defaults."""
import json
import os
from pathlib import Path
import sys

from acquire_delivery import (DeliveryError, bounded_json, expected_package,
                              sha256, validate_manifest, windows_delivery)
from build import PROJECT, output


def install_for_core(project=PROJECT, environ=None):
    environ = os.environ if environ is None else environ
    if (sys.platform != 'win32' or environ.get('GITHUB_ACTIONS') != 'true' or
            environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'):
        raise DeliveryError('hosted_windows_required', 'install')
    project = Path(project).resolve(strict=True)
    expected = expected_package(project, environ.get('AA_SOURCE_TAG', ''),
                                'win-x64', trusted=project)
    packages = project / 'packages'
    installer = packages / expected['package_name']
    if (packages.is_symlink() or not packages.resolve().is_relative_to(project) or
            installer.is_symlink() or not installer.is_file() or
            not installer.resolve().is_relative_to(packages.resolve()) or
            not 0 < installer.stat().st_size <= 2 << 30):
        raise DeliveryError('invalid_task_installer', 'install')
    manifest_file = packages / expected['manifest_name']
    manifest = bounded_json(manifest_file)
    validate_manifest(manifest, expected)
    if str(manifest['workflow_run']) != environ.get('GITHUB_RUN_ID'):
        raise DeliveryError('unexpected_installation_workflow', 'install')
    before = sha256(installer)
    # Reuse the same clean-identity, default per-user installer and x64/version
    # checks as fresh delivery. It refuses existing Chromium and preserves Chrome.
    browser, installed = windows_delivery(installer, expected, environ=environ)
    if sha256(installer) != before:
        raise DeliveryError('installer_changed_during_install', 'install')
    if sha256(browser) != installed['executable_sha256']:
        raise DeliveryError('installed_executable_changed', 'install')
    receipt = {'source_commit': expected['source_commit'],
               'source_tag': expected['source_tag'],
               'installer_sha256': before, 'browser': str(browser), **installed,
               'scope': 'Actual default per-user package installation for core checks; behavior is verified separately.'}
    manifest['windows_core_installation'] = receipt
    manifest_file.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return browser, receipt


if __name__ == '__main__':
    browser, receipt = install_for_core()
    output('browser', browser)
    print(json.dumps(receipt, indent=2))
