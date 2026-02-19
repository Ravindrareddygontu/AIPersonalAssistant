import pytest
import sys
import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from backend.app import app


client = TestClient(app)


class TestBrowseDirectories:

    def test_browse_home_directory(self):
        response = client.get('/api/browse')
        assert response.status_code == 200
        data = response.json()
        assert 'current' in data
        assert 'items' in data
        assert isinstance(data['items'], list)

    def test_browse_specific_path(self):
        response = client.get('/api/browse?path=/tmp')
        assert response.status_code == 200
        data = response.json()
        assert data['current'] == '/tmp'
        assert 'items' in data

    def test_browse_invalid_path_falls_back_to_home(self):
        response = client.get('/api/browse?path=/nonexistent/path/xyz')
        assert response.status_code == 200
        data = response.json()
        assert 'current' in data
        assert data['current'] != '/nonexistent/path/xyz'

    def test_browse_items_have_required_fields(self):
        response = client.get('/api/browse')
        assert response.status_code == 200
        data = response.json()
        if data['items']:
            item = data['items'][0]
            assert 'name' in item
            assert 'path' in item
            assert 'type' in item
            assert 'display_path' in item
            assert item['type'] == 'directory'

    def test_browse_excludes_hidden_folders(self):
        response = client.get('/api/browse')
        assert response.status_code == 200
        data = response.json()
        for item in data['items']:
            assert not item['name'].startswith('.')


class TestSearchFolders:

    def test_search_requires_minimum_query_length(self):
        response = client.get('/api/search-folders?query=a')
        assert response.status_code == 200
        data = response.json()
        assert data['items'] == []

    def test_search_empty_query_returns_empty(self):
        response = client.get('/api/search-folders?query=')
        assert response.status_code == 200
        data = response.json()
        assert data['items'] == []

    def test_search_returns_matching_folders(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, 'test_folder_abc'))
            os.makedirs(os.path.join(tmpdir, 'another_folder'))
            
            response = client.get(f'/api/search-folders?query=abc&path={tmpdir}')
            assert response.status_code == 200
            data = response.json()
            assert len(data['items']) >= 1
            assert any('abc' in item['name'].lower() for item in data['items'])

    def test_search_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, 'TestFolder'))
            
            response = client.get(f'/api/search-folders?query=testfolder&path={tmpdir}')
            assert response.status_code == 200
            data = response.json()
            assert len(data['items']) >= 1

    def test_search_excludes_hidden_folders(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, '.hidden_folder'))
            os.makedirs(os.path.join(tmpdir, 'visible_folder'))
            
            response = client.get(f'/api/search-folders?query=folder&path={tmpdir}')
            assert response.status_code == 200
            data = response.json()
            for item in data['items']:
                assert not item['name'].startswith('.')

    def test_search_results_have_display_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, 'searchable'))
            
            response = client.get(f'/api/search-folders?query=searchable&path={tmpdir}')
            assert response.status_code == 200
            data = response.json()
            if data['items']:
                item = data['items'][0]
                assert 'display_path' in item

    def test_search_recursive_finds_nested_folders(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = os.path.join(tmpdir, 'level1', 'level2', 'target_folder')
            os.makedirs(nested_path)
            
            response = client.get(f'/api/search-folders?query=target&path={tmpdir}')
            assert response.status_code == 200
            data = response.json()
            assert len(data['items']) >= 1
            assert any('target' in item['name'].lower() for item in data['items'])

    def test_search_limits_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(60):
                os.makedirs(os.path.join(tmpdir, f'match_{i}'))
            
            response = client.get(f'/api/search-folders?query=match&path={tmpdir}')
            assert response.status_code == 200
            data = response.json()
            assert len(data['items']) <= 50

