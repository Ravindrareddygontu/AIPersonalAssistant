import json
import os
import pytest
import shutil
import tempfile
from datetime import datetime, timedelta

from backend.storage.file_storage import FileStorage
from backend.storage.collections import (
    BaseCollection, ChatsCollection, RemindersCollection, BotChatsCollection,
    InsertResult, UpdateResult, DeleteResult
)
from backend.storage.index import StorageIndex


@pytest.fixture
def temp_storage_dir():
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def file_storage(temp_storage_dir):
    return FileStorage(temp_storage_dir)


@pytest.fixture
def chats_collection(file_storage):
    return ChatsCollection(file_storage)


@pytest.fixture
def bot_chats_collection(file_storage):
    return BotChatsCollection(file_storage)


class TestFileStorage:
    def test_init_creates_base_dir(self, temp_storage_dir):
        base_dir = os.path.join(temp_storage_dir, 'new_storage')
        storage = FileStorage(base_dir)
        assert os.path.exists(base_dir)

    def test_write_and_read(self, file_storage):
        data = {'id': 'test123', 'title': 'Test Chat', 'created_at': datetime.utcnow().isoformat()}
        assert file_storage.write('chats', 'test123', data)
        
        result = file_storage.read('chats', 'test123')
        assert result is not None
        assert result['id'] == 'test123'
        assert result['title'] == 'Test Chat'

    def test_read_nonexistent(self, file_storage):
        result = file_storage.read('chats', 'nonexistent')
        assert result is None

    def test_delete(self, file_storage):
        data = {'id': 'del123', 'created_at': datetime.utcnow().isoformat()}
        file_storage.write('chats', 'del123', data)
        
        assert file_storage.delete('chats', 'del123')
        assert file_storage.read('chats', 'del123') is None

    def test_delete_nonexistent(self, file_storage):
        assert file_storage.delete('chats', 'nonexistent') is False

    def test_list_all(self, file_storage):
        now = datetime.utcnow().isoformat()
        file_storage.write('chats', 'chat1', {'id': 'chat1', 'created_at': now})
        file_storage.write('chats', 'chat2', {'id': 'chat2', 'created_at': now})
        
        all_docs = file_storage.list_all('chats')
        assert len(all_docs) == 2
        ids = [d['id'] for d in all_docs]
        assert 'chat1' in ids
        assert 'chat2' in ids

    def test_file_path_structure(self, file_storage):
        created_at = '2026-02-21T10:30:00'
        path = file_storage.get_file_path('chats', 'abc123', created_at)
        assert '2026' in path
        assert '02' in path
        assert '21' in path
        assert 'abc123.json' in path


class TestStorageIndex:
    def test_set_and_get(self, temp_storage_dir):
        index = StorageIndex(temp_storage_dir, 'test')
        index.load()
        
        index.set('doc1', '/path/to/doc1.json', '2026-01-01', '2026-01-02')
        assert index.get('doc1') == '/path/to/doc1.json'

    def test_delete(self, temp_storage_dir):
        index = StorageIndex(temp_storage_dir, 'test')
        index.load()
        
        index.set('doc1', '/path/to/doc1.json')
        assert index.delete('doc1')
        assert index.get('doc1') is None

    def test_all_ids(self, temp_storage_dir):
        index = StorageIndex(temp_storage_dir, 'test')
        index.load()
        
        index.set('doc1', '/path/1.json')
        index.set('doc2', '/path/2.json')
        
        ids = index.all_ids()
        assert len(ids) == 2
        assert 'doc1' in ids
        assert 'doc2' in ids

    def test_save_and_reload(self, temp_storage_dir):
        index = StorageIndex(temp_storage_dir, 'test')
        index.load()
        index.set('doc1', '/path/to/doc1.json')
        index.save()
        
        index2 = StorageIndex(temp_storage_dir, 'test')
        index2.load()
        assert index2.get('doc1') == '/path/to/doc1.json'


class TestBaseCollection:
    def test_insert_one(self, chats_collection):
        result = chats_collection.insert_one({'title': 'New Chat'})
        assert isinstance(result, InsertResult)
        assert result.inserted_id is not None
        assert result.acknowledged

    def test_insert_one_preserves_id(self, chats_collection):
        result = chats_collection.insert_one({'id': 'custom123', 'title': 'Test'})
        assert result.inserted_id == 'custom123'

    def test_find_one(self, chats_collection):
        chats_collection.insert_one({'id': 'find1', 'title': 'Find Me'})
        
        result = chats_collection.find_one({'id': 'find1'})
        assert result is not None
        assert result['title'] == 'Find Me'

    def test_find_one_not_found(self, chats_collection):
        result = chats_collection.find_one({'id': 'nonexistent'})
        assert result is None

    def test_find_with_filter(self, chats_collection):
        chats_collection.insert_one({'id': 'c1', 'status': 'active'})
        chats_collection.insert_one({'id': 'c2', 'status': 'inactive'})
        chats_collection.insert_one({'id': 'c3', 'status': 'active'})

        results = chats_collection.find({'status': 'active'})
        assert len(results) == 2

    def test_find_with_sort_ascending(self, chats_collection):
        chats_collection.insert_one({'id': 'c1', 'created_at': '2026-01-03'})
        chats_collection.insert_one({'id': 'c2', 'created_at': '2026-01-01'})
        chats_collection.insert_one({'id': 'c3', 'created_at': '2026-01-02'})

        results = chats_collection.find(sort=[('created_at', 1)])
        assert len(results) == 3
        assert results[0]['id'] == 'c2'
        assert results[1]['id'] == 'c3'
        assert results[2]['id'] == 'c1'

    def test_find_with_sort_descending(self, chats_collection):
        chats_collection.insert_one({'id': 'c1', 'created_at': '2026-01-03'})
        chats_collection.insert_one({'id': 'c2', 'created_at': '2026-01-01'})
        chats_collection.insert_one({'id': 'c3', 'created_at': '2026-01-02'})

        results = chats_collection.find(sort=[('created_at', -1)])
        assert len(results) == 3
        assert results[0]['id'] == 'c1'
        assert results[1]['id'] == 'c3'
        assert results[2]['id'] == 'c2'

    def test_find_with_limit(self, chats_collection):
        for i in range(5):
            chats_collection.insert_one({'id': f'c{i}', 'created_at': f'2026-01-0{i+1}'})

        results = chats_collection.find(limit=3)
        assert len(results) == 3

    def test_find_with_sort_and_limit(self, chats_collection):
        chats_collection.insert_one({'id': 'c1', 'created_at': '2026-01-03'})
        chats_collection.insert_one({'id': 'c2', 'created_at': '2026-01-01'})
        chats_collection.insert_one({'id': 'c3', 'created_at': '2026-01-02'})

        results = chats_collection.find(sort=[('created_at', -1)], limit=2)
        assert len(results) == 2
        assert results[0]['id'] == 'c1'
        assert results[1]['id'] == 'c3'

    def test_update_one(self, chats_collection):
        chats_collection.insert_one({'id': 'u1', 'title': 'Original'})

        result = chats_collection.update_one({'id': 'u1'}, {'$set': {'title': 'Updated'}})
        assert isinstance(result, UpdateResult)
        assert result.matched_count == 1
        assert result.modified_count == 1

        doc = chats_collection.find_one({'id': 'u1'})
        assert doc['title'] == 'Updated'

    def test_update_one_not_found(self, chats_collection):
        result = chats_collection.update_one({'id': 'nonexistent'}, {'$set': {'title': 'X'}})
        assert result.matched_count == 0
        assert result.modified_count == 0

    def test_update_one_upsert(self, chats_collection):
        result = chats_collection.update_one(
            {'id': 'new1'},
            {'$set': {'title': 'Upserted'}},
            upsert=True
        )
        assert result.upserted_id is not None

        doc = chats_collection.find_one({'id': 'new1'})
        assert doc is not None
        assert doc['title'] == 'Upserted'

    def test_delete_one(self, chats_collection):
        chats_collection.insert_one({'id': 'd1', 'title': 'Delete Me'})

        result = chats_collection.delete_one({'id': 'd1'})
        assert isinstance(result, DeleteResult)
        assert result.deleted_count == 1

        assert chats_collection.find_one({'id': 'd1'}) is None

    def test_delete_many(self, chats_collection):
        chats_collection.insert_one({'id': 'd1', 'status': 'old'})
        chats_collection.insert_one({'id': 'd2', 'status': 'old'})
        chats_collection.insert_one({'id': 'd3', 'status': 'new'})

        result = chats_collection.delete_many({'status': 'old'})
        assert result.deleted_count == 2

        remaining = chats_collection.find()
        assert len(remaining) == 1
        assert remaining[0]['id'] == 'd3'

    def test_count_documents(self, chats_collection):
        chats_collection.insert_one({'id': 'c1', 'status': 'active'})
        chats_collection.insert_one({'id': 'c2', 'status': 'inactive'})
        chats_collection.insert_one({'id': 'c3', 'status': 'active'})

        assert chats_collection.count_documents() == 3
        assert chats_collection.count_documents({'status': 'active'}) == 2

    def test_filter_operators_gt(self, chats_collection):
        chats_collection.insert_one({'id': 'c1', 'count': 5})
        chats_collection.insert_one({'id': 'c2', 'count': 10})
        chats_collection.insert_one({'id': 'c3', 'count': 15})

        results = chats_collection.find({'count': {'$gt': 7}})
        assert len(results) == 2

    def test_filter_operators_in(self, chats_collection):
        chats_collection.insert_one({'id': 'c1', 'status': 'active'})
        chats_collection.insert_one({'id': 'c2', 'status': 'pending'})
        chats_collection.insert_one({'id': 'c3', 'status': 'closed'})

        results = chats_collection.find({'status': {'$in': ['active', 'pending']}})
        assert len(results) == 2

    def test_update_push(self, chats_collection):
        chats_collection.insert_one({'id': 'p1', 'messages': []})

        chats_collection.update_one({'id': 'p1'}, {'$push': {'messages': {'text': 'Hello'}}})

        doc = chats_collection.find_one({'id': 'p1'})
        assert len(doc['messages']) == 1
        assert doc['messages'][0]['text'] == 'Hello'

    def test_update_inc(self, chats_collection):
        chats_collection.insert_one({'id': 'i1', 'count': 5})

        chats_collection.update_one({'id': 'i1'}, {'$inc': {'count': 3}})

        doc = chats_collection.find_one({'id': 'i1'})
        assert doc['count'] == 8


class TestBotChatsCollection:
    def test_find_one_and_update(self, bot_chats_collection):
        bot_chats_collection.insert_one({'id': 'bot1', 'title': 'Original'})

        result = bot_chats_collection.find_one_and_update(
            {'id': 'bot1'},
            {'$set': {'title': 'Updated'}},
            return_document='after'
        )
        assert result is not None
        assert result['title'] == 'Updated'

    def test_find_one_and_update_upsert(self, bot_chats_collection):
        result = bot_chats_collection.find_one_and_update(
            {'lookup_key': 'slack:123'},
            {'$set': {'title': 'New Bot Chat'}},
            upsert=True,
            return_document='after'
        )
        assert result is not None
        assert result['title'] == 'New Bot Chat'
        assert result['lookup_key'] == 'slack:123'

    def test_create_index_noop(self, bot_chats_collection):
        bot_chats_collection.create_index('lookup_key', unique=True)


class TestEdgeCases:
    def test_sort_with_none_values(self, chats_collection):
        chats_collection.insert_one({'id': 'c1', 'created_at': '2026-01-02'})
        chats_collection.insert_one({'id': 'c2'})  # No created_at
        chats_collection.insert_one({'id': 'c3', 'created_at': '2026-01-01'})

        results = chats_collection.find(sort=[('created_at', 1)])
        assert len(results) == 3

    def test_sort_with_missing_field(self, chats_collection):
        chats_collection.insert_one({'id': 'c1', 'title': 'B'})
        chats_collection.insert_one({'id': 'c2', 'title': 'A'})
        chats_collection.insert_one({'id': 'c3'})  # No title

        results = chats_collection.find(sort=[('title', 1)])
        assert len(results) == 3

    def test_empty_collection(self, chats_collection):
        results = chats_collection.find()
        assert results == []

        results = chats_collection.find(sort=[('created_at', -1)])
        assert results == []

    def test_multiple_sort_fields(self, chats_collection):
        chats_collection.insert_one({'id': 'c1', 'status': 'a', 'priority': 2})
        chats_collection.insert_one({'id': 'c2', 'status': 'a', 'priority': 1})
        chats_collection.insert_one({'id': 'c3', 'status': 'b', 'priority': 1})

        results = chats_collection.find(sort=[('status', 1), ('priority', 1)])
        assert results[0]['id'] == 'c2'  # status=a, priority=1
        assert results[1]['id'] == 'c1'  # status=a, priority=2
        assert results[2]['id'] == 'c3'  # status=b, priority=1

    def test_filter_with_none_value(self, chats_collection):
        chats_collection.insert_one({'id': 'c1', 'status': None})
        chats_collection.insert_one({'id': 'c2', 'status': 'active'})

        results = chats_collection.find({'status': None})
        assert len(results) == 1
        assert results[0]['id'] == 'c1'

    def test_update_preserves_other_fields(self, chats_collection):
        chats_collection.insert_one({'id': 'u1', 'title': 'Test', 'messages': [1, 2, 3]})

        chats_collection.update_one({'id': 'u1'}, {'$set': {'title': 'Updated'}})

        doc = chats_collection.find_one({'id': 'u1'})
        assert doc['title'] == 'Updated'
        assert doc['messages'] == [1, 2, 3]

    def test_concurrent_write_safety(self, file_storage):
        import threading
        results = []

        def write_doc(i):
            try:
                data = {'id': f'concurrent{i}', 'created_at': datetime.utcnow().isoformat()}
                file_storage.write('chats', f'concurrent{i}', data)
                results.append(True)
            except Exception as e:
                results.append(False)

        threads = [threading.Thread(target=write_doc, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(results)
        assert len(file_storage.list_all('chats')) == 10

    def test_special_characters_in_content(self, chats_collection):
        special_content = 'Test with "quotes" and \'apostrophes\' and\nnewlines'
        chats_collection.insert_one({'id': 'special', 'content': special_content})

        doc = chats_collection.find_one({'id': 'special'})
        assert doc['content'] == special_content

    def test_unicode_content(self, chats_collection):
        unicode_content = '日本語 🎉 مرحبا émojis'
        chats_collection.insert_one({'id': 'unicode', 'content': unicode_content})

        doc = chats_collection.find_one({'id': 'unicode'})
        assert doc['content'] == unicode_content

    def test_large_document(self, chats_collection):
        large_messages = [{'text': f'Message {i}', 'data': 'x' * 1000} for i in range(100)]
        chats_collection.insert_one({'id': 'large', 'messages': large_messages})

        doc = chats_collection.find_one({'id': 'large'})
        assert len(doc['messages']) == 100

    def test_find_all_no_filter(self, chats_collection):
        chats_collection.insert_one({'id': 'c1'})
        chats_collection.insert_one({'id': 'c2'})

        results = chats_collection.find(None)
        assert len(results) == 2

        results = chats_collection.find({})
        assert len(results) == 2


class TestAPICompatibility:
    def test_chat_list_sort_pattern(self, chats_collection):
        chats_collection.insert_one({'id': 'c1', 'created_at': '2026-02-21T10:00:00'})
        chats_collection.insert_one({'id': 'c2', 'created_at': '2026-02-21T08:00:00'})
        chats_collection.insert_one({'id': 'c3', 'created_at': '2026-02-21T09:00:00'})

        results = chats_collection.find(sort=[('created_at', -1)])

        assert len(results) == 3
        assert results[0]['id'] == 'c1'  # newest
        assert results[1]['id'] == 'c3'
        assert results[2]['id'] == 'c2'  # oldest

    def test_chat_structure_compatibility(self, chats_collection):
        chat = {
            'id': 'api_chat',
            'title': 'Test Chat',
            'created_at': '2026-02-21T10:00:00',
            'updated_at': '2026-02-21T10:00:00',
            'messages': [
                {'id': 'msg1', 'question': 'Hello', 'answer': 'Hi there'}
            ],
            'workspace': '/home/user/project',
            'streaming_status': None
        }

        result = chats_collection.insert_one(chat)
        assert result.inserted_id == 'api_chat'

        loaded = chats_collection.find_one({'id': 'api_chat'})
        assert loaded['title'] == 'Test Chat'
        assert loaded['workspace'] == '/home/user/project'
        assert len(loaded['messages']) == 1

    def test_update_messages_push(self, chats_collection):
        chats_collection.insert_one({
            'id': 'msg_chat',
            'title': 'Chat',
            'messages': []
        })

        chats_collection.update_one(
            {'id': 'msg_chat'},
            {'$push': {'messages': {'id': 'm1', 'question': 'Q1', 'answer': None}}}
        )

        chat = chats_collection.find_one({'id': 'msg_chat'})
        assert len(chat['messages']) == 1

        chats_collection.update_one(
            {'id': 'msg_chat'},
            {'$set': {'messages': [
                {'id': 'm1', 'question': 'Q1', 'answer': 'A1'}
            ]}}
        )

        chat = chats_collection.find_one({'id': 'msg_chat'})
        assert chat['messages'][0]['answer'] == 'A1'

    def test_title_auto_update(self, chats_collection):
        chats_collection.insert_one({'id': 't1', 'title': 'New Chat'})

        chat = chats_collection.find_one({'id': 't1'})
        assert chat['title'] == 'New Chat'

        question = 'What is the meaning of life?'
        new_title = question[:50] + ('...' if len(question) > 50 else '')

        chats_collection.update_one(
            {'id': 't1', 'title': 'New Chat'},
            {'$set': {'title': new_title}}
        )

        chat = chats_collection.find_one({'id': 't1'})
        assert chat['title'] == question


class TestRobustness:
    def test_read_empty_doc_id(self, file_storage):
        result = file_storage.read('chats', '')
        assert result is None

        result = file_storage.read('chats', None)
        assert result is None

    def test_write_empty_doc_id(self, file_storage):
        result = file_storage.write('chats', '', {'title': 'Test'})
        assert result is False

    def test_write_non_dict_data(self, file_storage):
        result = file_storage.write('chats', 'test', "not a dict")
        assert result is False

        result = file_storage.write('chats', 'test', ['list'])
        assert result is False

    def test_invalid_created_at_format(self, file_storage):
        data = {'id': 'test', 'created_at': 'invalid-date'}
        result = file_storage.write('chats', 'test', data)
        assert result is True

        loaded = file_storage.read('chats', 'test')
        assert loaded is not None

    def test_special_characters_in_doc_id(self, file_storage):
        data = {'id': 'test/with\\special:chars?', 'created_at': datetime.utcnow().isoformat()}
        result = file_storage.write('chats', 'test/with\\special:chars?', data)
        assert result is True

    def test_very_long_doc_id(self, file_storage):
        long_id = 'a' * 200
        data = {'id': long_id, 'created_at': datetime.utcnow().isoformat()}
        result = file_storage.write('chats', long_id, data)
        assert result is True

    def test_index_persistence_after_crash_simulation(self, temp_storage_dir):
        storage1 = FileStorage(temp_storage_dir)
        now = datetime.utcnow().isoformat()
        storage1.write('chats', 'persist1', {'id': 'persist1', 'created_at': now})
        storage1.write('chats', 'persist2', {'id': 'persist2', 'created_at': now})

        storage2 = FileStorage(temp_storage_dir)

        doc1 = storage2.read('chats', 'persist1')
        doc2 = storage2.read('chats', 'persist2')
        assert doc1 is not None
        assert doc2 is not None

    def test_corrupted_json_handling(self, temp_storage_dir):
        storage = FileStorage(temp_storage_dir)
        now = datetime.utcnow().isoformat()
        storage.write('chats', 'corrupt', {'id': 'corrupt', 'created_at': now})

        index = storage.get_index('chats')
        path = index.get('corrupt')

        with open(path, 'w') as f:
            f.write('{ invalid json }}}')

        result = storage.read('chats', 'corrupt')
        assert result is None

    def test_delete_nonexistent_then_recreate(self, file_storage):
        assert file_storage.delete('chats', 'ghost') is False

        now = datetime.utcnow().isoformat()
        file_storage.write('chats', 'ghost', {'id': 'ghost', 'created_at': now})

        doc = file_storage.read('chats', 'ghost')
        assert doc is not None
        assert doc['id'] == 'ghost'

