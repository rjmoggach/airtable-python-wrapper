import pytest
from posixpath import join as urljoin
from requests_mock import Mocker
from urllib.parse import urlencode

from airtable import Airtable


def test_repr(table):
    assert "<Airtable" in table.__repr__()


@pytest.mark.parametrize(
    "base_id,table_name,table_url_suffix",
    [
        ("abc", "My Table", "abc/My%20Table"),
        ("abc", "SomeTable", "abc/SomeTable"),
        ("abc", "Table-fake", "abc/Table-fake"),
    ],
)
def test_url(base_id, table_name, table_url_suffix):
    table = Airtable(base_id, table_name, api_key="x")
    assert table.url_table == "{0}/{1}".format(table.API_URL, table_url_suffix)


def test_chunk(table):
    chunks = [chunk for chunk in table._chunk([0, 0, 1, 1, 2, 2, 3], 2)]
    assert chunks[0] == [0, 0]
    assert chunks[1] == [1, 1]
    assert chunks[2] == [2, 2]
    assert chunks[3] == [3]


def test_record_url(table):
    rv = table.record_url("xxx")
    assert rv == urljoin(table.url_table, "xxx")


def test_get(table, mock_response_single):
    _id = mock_response_single["id"]
    with Mocker() as mock:
        mock.get(table.record_url(_id), status_code=200, json=mock_response_single)
        resp = table.get(_id)
    # assert sorted(resp.items()) == sorted(mock_response_single.items())
    assert dict_equals(resp, mock_response_single)


def test_get_all(table, mock_response_list, mock_records):
    with Mocker() as mock:
        mock.get(
            table.url_table,
            status_code=200,
            json=mock_response_list[0],
            complete_qs=True,
        )
        for n, resp in enumerate(mock_response_list, 1):
            offset = resp.get("offset", None)
            if not offset:
                continue
            offset_url = table.url_table + "?offset={}".format(offset)
            mock.get(
                offset_url,
                status_code=200,
                json=mock_response_list[1],
                complete_qs=True,
            )
        response = table.get_all()

    for n, resp in enumerate(response):
        # assert sorted(resp.items()) == sorted(mock_records[n].items())
        assert dict_equals(resp, mock_records[n])


def test_insert(table, mock_response_single):
    with Mocker() as mock:
        post_data = mock_response_single["fields"]
        mock.post(
            table.url_table,
            status_code=201,
            json=mock_response_single,
            additional_matcher=match_request_data(post_data),
        )
        resp = table.insert(post_data)
    assert dict_equals(resp, mock_response_single)


def test_match(table, mock_response_single):
    params = urlencode({"FilterByFormula": "{Value}='abc'"})
    with Mocker() as mock:
        mock.get(
            table.url_table + "?" + params,
            status_code=200,
            json={"records": [mock_response_single, mock_response_single]},
        )
        resp = table.match("Value", "abc")
    assert resp == mock_response_single


def test_match_not_found(table, mock_response_single):
    params = urlencode({"FilterByFormula": "{Value}='abc'"})
    with Mocker() as mock:
        mock.get(table.url_table + "?" + params, status_code=200, json={"records": []})
        resp = table.match("Value", "abc")
    assert resp == {}


def test_search(table, mock_response_single):
    expected = [mock_response_single, mock_response_single]
    params = urlencode({"FilterByFormula": "{Value}='abc'"})
    with Mocker() as mock:
        mock.get(
            table.url_table + "?" + params, status_code=200, json={"records": expected}
        )
        resp = table.search("Value", "abc")
    assert resp == expected


def test_search_not_found(table, mock_response_single):
    params = urlencode({"FilterByFormula": "{Value}='abc'"})
    with Mocker() as mock:
        mock.get(table.url_table + "?" + params, status_code=200, json={"records": []})
        resp = table.search("Value", "abc")
    assert resp == []


def test_batch_insert(table, mock_records):
    with Mocker() as mock:
        for chunk in _chunk(mock_records, 10):
            mock.post(
                table.url_table, status_code=201, json={"records": chunk},
            )
        records = [i["fields"] for i in mock_records]
        resp = table.batch_insert(records)
    assert seq_equals(resp, mock_records)


def test_update(table, mock_response_single):
    id_ = mock_response_single["id"]
    post_data = mock_response_single["fields"]
    with Mocker() as mock:
        mock.patch(
            urljoin(table.url_table, id_),
            status_code=201,
            json=mock_response_single,
            additional_matcher=match_request_data(post_data),
        )
        resp = table.update(id_, post_data)
    assert dict_equals(resp, mock_response_single)


def test_batch_update(table, mock_response_batch):
    records = [{"id": x["id"], "fields": x["fields"]} for x in mock_response_batch["records"]]
    with Mocker() as mock:
        for chunk in _chunk(mock_response_batch["records"], 10):
            mock.patch(
                table.url_table, status_code=201, json={"records": chunk},
            )
        #
        resp = table.batch_update(records)
    assert resp == mock_response_batch["records"]


def test_update_by_field(table, mock_response_single):
    id_ = mock_response_single["id"]
    post_data = mock_response_single["fields"]
    match_params = urlencode({"FilterByFormula": "{Value}='abc'"})
    match_url = table.url_table + "?" + match_params
    with Mocker() as mock:
        mock.get(
            match_url,
            status_code=200,
            json={"records": [mock_response_single, mock_response_single]},
        )
        mock.patch(
            urljoin(table.url_table, id_),
            status_code=201,
            json=mock_response_single,
            additional_matcher=match_request_data(post_data),
        )
        resp = table.update_by_field("Value", "abc", post_data)
    assert dict_equals(resp, mock_response_single)


def test_replace(table, mock_response_single):
    id_ = mock_response_single["id"]
    post_data = mock_response_single["fields"]
    with Mocker() as mock:
        mock.put(
            urljoin(table.url_table, id_),
            status_code=201,
            json=mock_response_single,
            additional_matcher=match_request_data(post_data),
        )
        resp = table.replace(id_, post_data)
    assert dict_equals(resp, mock_response_single)


def test_replace_by_field(table, mock_response_single):
    id_ = mock_response_single["id"]
    post_data = mock_response_single["fields"]
    match_params = urlencode({"FilterByFormula": "{Value}='abc'"})
    match_url = table.url_table + "?" + match_params
    with Mocker() as mock:
        mock.get(
            match_url,
            status_code=200,
            json={"records": [mock_response_single, mock_response_single]},
        )
        mock.put(
            urljoin(table.url_table, id_),
            status_code=201,
            json=mock_response_single,
            additional_matcher=match_request_data(post_data),
        )
        resp = table.replace_by_field("Value", "abc", post_data)
    assert dict_equals(resp, mock_response_single)


def test_delete(table, mock_response_single):
    id_ = mock_response_single["id"]
    expected = {"delete": True, "id": id_}
    with Mocker() as mock:
        mock.delete(urljoin(table.url_table, id_), status_code=201, json=expected)
        resp = table.delete(id_)
    assert resp == expected


def test_delete_by_field(table, mock_response_single):
    id_ = mock_response_single["id"]
    expected = {"delete": True, "id": id_}
    match_params = urlencode({"FilterByFormula": "{Value}='abc'"})
    match_url = table.url_table + "?" + match_params
    with Mocker() as mock:
        mock.get(
            match_url,
            status_code=200,
            json={"records": [mock_response_single, mock_response_single]},
        )
        mock.delete(urljoin(table.url_table, id_), status_code=201, json=expected)
        resp = table.delete_by_field("value", "abc")
    assert resp == expected


def test_batch_delete(table, mock_records):
    ids = [i["id"] for i in mock_records]
    with Mocker() as mock:
        for chunk in _chunk(ids, 10):
            params = [("records", id_) for id_ in chunk]
            params_encode = urlencode(params)
            json = (
                {"records": [{"delete": True, "id": id_} for id_ in chunk]}
                if len(chunk) > 1
                else {"delete": True, "id": chunk[0]}
            )
            url = (
                table.url_table + "?" + params_encode
                if len(chunk) > 1
                else urljoin(table.url_table, chunk[0])
            )
            mock.delete(
                url, status_code=201, json=json,
            )

        resp = table.batch_delete(ids)
    expected = [{"delete": True, "id": i} for i in ids]
    assert resp == expected


def test_batch_delete_single_record(table, mock_response_single):
    test_batch_delete(table, [mock_response_single])


# Helpers


def _chunk(iterable, chunk_size):
    for i in range(0, len(iterable), chunk_size):
        yield iterable[i : i + chunk_size]


def match_request_data(post_data):
    """ Custom Matches, check that provided Request data is correct"""

    def _match_request_data(request):
        request_data_fields = request.json()["fields"]
        return dict_equals(request_data_fields, post_data)

    return _match_request_data


def dict_equals(d1, d2):
    return sorted(d1.items()) == sorted(d2.items())


def seq_equals(s1, s2):
    return all(dict_equals(s1, s2) for s1, s2 in zip(s1, s2))
