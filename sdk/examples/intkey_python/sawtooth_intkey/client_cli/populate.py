#!/usr/bin/python
#
# Copyright 2016 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ------------------------------------------------------------------------------

import argparse
import hashlib
import os
import logging
import random
import string

import cbor
import bitcoin

import sawtooth_protobuf.batch_pb2 as batch_pb2
import sawtooth_protobuf.transaction_pb2 as transaction_pb2


LOGGER = logging.getLogger(__name__)


class IntKeyPayload(object):
    def __init__(self, verb, name, value):
        self._verb = verb
        self._name = name
        self._value = value

        self._cbor = None
        self._sha512 = None

    def to_hash(self):
        return {
            'Verb': self._verb,
            'Name': self._name,
            'Value': self._value
        }

    def to_cbor(self):
        if self._cbor is None:
            self._cbor = cbor.dumps(self.to_hash(), sort_keys=True)
        return self._cbor

    def sha512(self):
        if self._sha512 is None:
            self._sha512 = hashlib.sha512(self.to_cbor()).hexdigest()
        return self._sha512


def create_intkey_transaction(verb, name, value, private_key, public_key):
    payload = IntKeyPayload(
        verb=verb, name=name, value=value)

    # The prefix should eventually be looked up from the
    # validator's namespace registry.
    intkey_prefix = hashlib.sha512('intkey'.encode('utf-8')).hexdigest()[0:6]

    addr = intkey_prefix + hashlib.sha512(name.encode('utf-8')).hexdigest()

    header = transaction_pb2.TransactionHeader(
        signer_pubkey=public_key,
        family_name='intkey',
        family_version='1.0',
        inputs=[addr],
        outputs=[addr],
        dependencies=[],
        payload_encoding="application/cbor",
        payload_sha512=payload.sha512(),
        batcher_pubkey=public_key)

    header_bytes = header.SerializeToString()

    signature = bitcoin.ecdsa_sign(
        header_bytes,
        private_key)

    transaction = transaction_pb2.Transaction(
        header=header_bytes,
        payload=payload.to_cbor(),
        header_signature=signature)

    return transaction


def create_batch(transactions, private_key, public_key):
    transaction_ids = [t.header_signature for t in transactions]

    header = batch_pb2.BatchHeader(
        signer_pubkey=public_key,
        transaction_ids=transaction_ids)

    header_bytes = header.SerializeToString()

    signature = bitcoin.ecdsa_sign(
        header_bytes,
        private_key)

    batch = batch_pb2.Batch(
        header=header_bytes,
        transactions=transactions,
        header_signature=signature)

    return batch


def generate_word():
    return ''.join([random.choice(string.ascii_letters) for _ in range(0, 6)])


def generate_word_list(count):
    if os.path.isfile('/usr/share/dict/words'):
        with open('/usr/share/dict/words', 'r') as fd:
            return [x.strip() for x in fd.readlines()[0:count]]
    else:
        return [generate_word() for _ in range(0, count)]


def do_populate(args):
    private_key = bitcoin.random_key()
    public_key = bitcoin.encode_pubkey(
        bitcoin.privkey_to_pubkey(private_key), "hex")

    words = generate_word_list(args.pool_size)

    batches = []
    total_txn_count = 0

    txns = []
    for i in range(0, len(words)):
        txn = create_intkey_transaction(
            verb='set',
            name=words[i],
            value=random.randint(9000, 100000),
            private_key=private_key,
            public_key=public_key)
        total_txn_count += 1
        txns.append(txn)

    batch = create_batch(
        transactions=txns,
        private_key=private_key,
        public_key=public_key)

    batches.append(batch)

    batch_list = batch_pb2.BatchList(batches=batches)

    print("Writing to {}...".format(args.output))
    with open(args.output, "wb") as fd:
        fd.write(batch_list.SerializeToString())


def add_populate_parser(subparsers, parent_parser):
    parser = subparsers.add_parser(
        'populate',
        parents=[parent_parser],
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument(
        '-o', '--output',
        type=str,
        help='location of output file',
        default='batches.intkey')

    parser.add_argument(
        '-P', '--pool-size',
        type=int,
        help='size of the word pool',
        default=100)