import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator

SCHEMA=Path(__file__).resolve().parents[1]/'src/wikidebia_validator/schemas/page_manifest.schema.json'


def test_owner_update_schema_requires_explicit_revision_bound_approval():
    schema=json.loads(SCHEMA.read_text())['properties']['existing_english_update'];validate=Draft202012Validator(schema)
    row=dict(language='en',page_id='A0007',title='An existing English page',owner_approved=True,
             decision='explicit_user_request',instruction='Update the two English pages and their existing quotations as discussed.',
             authorization_receipt_sha256='a'*64,reason='The owner approved the full reviewed replacement of this existing page.',
             allow_proposed_change=True,observed_revision_id=18530,observed_sha256='b'*64,
             allowed_lifecycle_parameter_changes=[],allowed_parameter_deletions=['citations'])
    assert not list(validate.iter_errors(row))
    for key,value in [('owner_approved',False),('decision','pending'),('language','fr'),('observed_revision_id',0),('observed_sha256','bad'),('instruction','')]:
        assert list(validate.iter_errors({**row,key:value})),key
    del row['authorization_receipt_sha256'];assert list(validate.iter_errors(row))
