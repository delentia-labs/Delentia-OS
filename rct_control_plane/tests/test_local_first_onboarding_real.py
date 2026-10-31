"""A wheel user needs no source tree or five running development services."""
import importlib
import json
from pathlib import Path

from click.testing import CliRunner

from rct_control_plane import model_config, setup_wizard
from rct_control_plane.cli import cli

cli_module = importlib.import_module('rct_control_plane.cli')


def test_default_doctor_does_not_probe_ports_or_require_source_files(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('installation doctor must not contact a service')
    monkeypatch.setattr(cli_module.socket, 'create_connection', forbidden)
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ['doctor', '--output', 'json'])
        assert result.exit_code == 0, result.output
        report = json.loads(result.output)
        assert report['ok'] and report['issues'] == 0
        assert report['scope'] == 'local_installation'
        assert not any(c['category'] in {'project', 'connectivity'} for c in report['checks'])
        assert 'provider billing' in report['not_checked']
        assert not Path('.env').exists()


def test_development_checks_are_explicit_and_keep_reporting_missing_services(monkeypatch):
    calls = []
    def offline(address, **kwargs):
        calls.append(address)
        raise OSError('offline fixture')
    monkeypatch.setattr(cli_module.socket, 'create_connection', offline)
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ['doctor', '--development', '--output', 'json'])
        report = json.loads(result.output)
        assert result.exit_code == 1
        assert report['scope'] == 'development' and not report['ok']
        assert [p for _, p in calls] == list(range(8000, 8005))
        assert any(c['name'] == 'pyproject.toml' and not c['ok'] for c in report['checks'])


def test_local_doctor_still_reports_missing_core_dependency(monkeypatch):
    original = cli_module._package_version
    monkeypatch.setattr(cli_module, '_package_version', lambda package: None if package == 'fastapi' else original(package))
    result = CliRunner().invoke(cli, ['doctor', '--output', 'json'])
    assert result.exit_code == 1
    report = json.loads(result.output)
    assert not report['ok'] and report['issues'] == 1
    assert any(c['name'] == 'fastapi' and not c['ok'] for c in report['checks'])


def test_local_doctor_table_explains_scope_and_free_first_task():
    result = CliRunner().invoke(cli, ['doctor'])
    assert result.exit_code == 0
    assert 'Scope: local installation' in result.output
    assert '--scripted' in result.output


def test_setup_and_model_config_share_environment_home_without_creating_it(tmp_path, monkeypatch):
    home = tmp_path / 'พื้นที่ส่วนตัว'
    monkeypatch.setenv('DELENTIA_HOME', str(home))
    monkeypatch.delenv('DELENTIA_MODEL_CONFIG', raising=False)
    assert setup_wizard.delentia_home() == home
    assert model_config.config_path() == home / 'model.json'
    assert not home.exists()


def test_explicit_home_and_model_config_overrides_remain_authoritative(tmp_path, monkeypatch):
    monkeypatch.setenv('DELENTIA_HOME', str(tmp_path / 'default'))
    config = tmp_path / 'chosen.json'
    monkeypatch.setenv('DELENTIA_MODEL_CONFIG', str(config))
    assert setup_wizard.delentia_home(str(tmp_path / 'trial')) == tmp_path / 'trial'
    assert model_config.config_path() == config


def test_no_environment_override_keeps_existing_user_home_default(monkeypatch):
    monkeypatch.delenv('DELENTIA_HOME', raising=False)
    monkeypatch.delenv('DELENTIA_MODEL_CONFIG', raising=False)
    assert setup_wizard.delentia_home() == Path.home() / '.delentia'
    assert model_config.config_path() == Path.home() / '.delentia' / 'model.json'


def test_setup_saved_model_is_visible_to_runtime_using_same_home(tmp_path, monkeypatch):
    from rct_control_plane import memory_embeddings
    home = tmp_path / 'user-data'
    monkeypatch.setenv('DELENTIA_HOME', str(home))
    monkeypatch.delenv('DELENTIA_MODEL_CONFIG', raising=False)
    monkeypatch.setattr(memory_embeddings, '_installed_models', lambda *a: [])
    result = CliRunner().invoke(cli, ['setup', '--yes', '--provider', 'ollama', '--model', 'fixture-local'])
    assert result.exit_code == 0, result.output
    config = model_config.load_model_config()
    assert config['provider'] == 'ollama' and config['model'] == 'fixture-local'
    assert (home / 'keys' / 'audit-signer.pem').exists()
    assert not (home / 'keys' / 'approver-trial.pem').exists()
