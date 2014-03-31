# -*- coding: utf-8 -*-
"""
PubChemPy

Python interface for the PubChem PUG REST service.
https://github.com/mcs07/PubChemPy
"""

import functools
import json
import logging
import os
import time

try:
    # Python 3
    from urllib.error import HTTPError
    from urllib.parse import quote, urlencode
    from urllib.request import urlopen
except ImportError:
    # Python 2
    from urllib2 import quote, urlopen, HTTPError
    from urlparse import urlencode


__author__ = 'Matt Swain'
__email__ = 'm.swain@me.com'
__version__ = '1.0.1'
__license__ = 'MIT'

API_BASE = 'https://pubchem.ncbi.nlm.nih.gov/rest/pug'

log = logging.getLogger('pubchempy')
log.addHandler(logging.NullHandler())


def request(identifier, namespace='cid', domain='compound', operation=None, output='JSON', searchtype=None, **kwargs):
    """
    Construct API request from parameters and return the response.

    Full specification at http://pubchem.ncbi.nlm.nih.gov/pug_rest/PUG_REST.html
    """

    # If identifier is a list, join with commas into string
    if isinstance(identifier, int):
        identifier = str(identifier)
    if not isinstance(identifier, (str, bytes)):
        identifier = ','.join(str(x) for x in identifier)

    # Filter None values from kwargs
    kwargs = dict((k, v) for k, v in kwargs.items() if v is not None)

    # Build API URL
    urlid, postdata = None, None
    if namespace == 'sourceid':
        identifier = identifier.replace('/', '.')
    if namespace in ['listkey', 'formula', 'sourceid'] or (searchtype and namespace == 'cid') or domain == 'sources':
        urlid = quote(identifier.encode('utf8'))
    else:
        postdata = ('%s=%s' % (namespace, quote(identifier.encode('utf8')))).encode('utf8')
    comps = filter(None, [API_BASE, domain, searchtype, namespace, urlid, operation, output])
    apiurl = '/'.join(comps)
    if kwargs:
        apiurl += '?%s' % urlencode(kwargs)

    # Make request
    try:
        log.debug('Request URL: %s', apiurl)
        log.debug('Request data: %s', postdata)
        response = urlopen(apiurl, postdata).read()
        return response
    except HTTPError as e:
        raise PubChemHTTPError(e)


def get(identifier, namespace='cid', domain='compound', operation=None, output='JSON', searchtype=None, **kwargs):
    """Request wrapper that automatically handles async requests."""
    if searchtype or namespace in ['formula']:
        response = request(identifier, namespace, domain, None, 'JSON', searchtype, **kwargs)
        status = json.loads(response.decode())
        if 'Waiting' in status and 'ListKey' in status['Waiting']:
            identifier = status['Waiting']['ListKey']
            namespace = 'listkey'
            while 'Waiting' in status and 'ListKey' in status['Waiting']:
                time.sleep(2)
                response = request(identifier, namespace, domain, operation, 'JSON', **kwargs)
                status = json.loads(response.decode())
            if not output == 'JSON':
                response = request(identifier, namespace, domain, operation, output, searchtype, **kwargs)
    else:
        response = request(identifier, namespace, domain, operation, output, searchtype, **kwargs)
    return response


def get_json(identifier, namespace='cid', domain='compound', operation=None, searchtype=None, **kwargs):
    """Request wrapper that automatically parses JSON response and supresses NotFoundError."""
    try:
        return json.loads(get(identifier, namespace, domain, operation, 'JSON', searchtype, **kwargs).decode())
    except NotFoundError as e:
        log.info(e)
        return None


def get_compounds(identifier, namespace='cid', searchtype=None, as_dataframe=False, **kwargs):
    """Retrieve the specified compound records from PubChem.

    :param identifier: The compound identifier to use as a search query.
    :param namespace: (optional) The identifier type, one of cid, name, smiles, sdf, inchi, inchikey or formula.
    :param searchtype: (optional) The advanced search type, one of substructure, superstructure or similarity.
    :param as_dataframe: (optional) Automatically extract the :class:`~pubchempy.Compound` properties into a pandas
                         :class:`~pandas.DataFrame` and return that.
    """
    results = get_json(identifier, namespace, searchtype=searchtype, **kwargs)
    compounds = [Compound(r) for r in results['PC_Compounds']] if results else []
    if as_dataframe:
        return compounds_to_frame(compounds)
    return compounds


def get_substances(identifier, namespace='sid', as_dataframe=False, **kwargs):
    """Retrieve the specified substance records from PubChem.

    :param identifier: The substance identifier to use as a search query.
    :param namespace: (optional) The identifier type, one of sid, name or sourceid/<source name>.
    :param as_dataframe: (optional) Automatically extract the :class:`~pubchempy.Substance` properties into a pandas
                         :class:`~pandas.DataFrame` and return that.
    """
    results = get_json(identifier, namespace, 'substance', **kwargs)
    substances = [Substance(r) for r in results['PC_Substances']] if results else []
    if as_dataframe:
        return substances_to_frame(substances)
    return substances


def get_assays(identifier, namespace='aid', **kwargs):
    """Retrieve the specified assay records from PubChem.

    :param identifier: The assay identifier to use as a search query.
    :param namespace: (optional) The identifier type.
    """
    results = get_json(identifier, namespace, 'assay', **kwargs)
    return [Assay(r) for r in results['PC_AssayContainer']] if results else []


# Allows properties to optionally be specified as underscore_separated, consistent with Compound attributes
PROPERTY_MAP = {
    'molecular_formula': 'MolecularFormula',
    'molecular_weight': 'MolecularWeight',
    'canonical_smiles': 'CanonicalSMILES',
    'isomeric_smiles': 'IsomericSMILES',
    'inchi': 'InChI',
    'inchikey': 'InChIKey',
    'iupac_name': 'IUPACName',
    'xlogp': 'XLogP',
    'exact_mass': 'ExactMass',
    'monoisotopic_mass': 'MonoisotopicMass',
    'tpsa': 'TPSA',
    'complexity': 'Complexity',
    'charge': 'Charge',
    'h_bond_donor_count': 'HBondDonorCount',
    'h_bond_acceptor_count': 'HBondAcceptorCount',
    'rotatable_bond_count': 'RotatableBondCount',
    'heavy_atom_count': 'HeavyAtomCount',
    'isotope_atom_count': 'IsotopeAtomCount',
    'atom_stereo_count': 'AtomStereoCount',
    'defined_atom_stereo_count': 'DefinedAtomStereoCount',
    'undefined_atom_stereo_count': 'UndefinedAtomStereoCount',
    'bond_stereo_count': 'BondStereoCount',
    'defined_bond_stereo_count': 'DefinedBondStereoCount',
    'undefined_bond_stereo_count': 'UndefinedBondStereoCount',
    'covalent_unit_count': 'CovalentUnitCount',
    'volume_3d': 'Volume3D',
    'conformer_rmsd_3d': 'ConformerModelRMSD3D',
    'conformer_model_rmsd_3d': 'ConformerModelRMSD3D',
    'x_steric_quadrupole_3d': 'XStericQuadrupole3D',
    'y_steric_quadrupole_3d': 'YStericQuadrupole3D',
    'z_steric_quadrupole_3d': 'ZStericQuadrupole3D',
    'feature_count_3d': 'FeatureCount3D',
    'feature_acceptor_count_3d': 'FeatureAcceptorCount3D',
    'feature_donor_count_3d': 'FeatureDonorCount3D',
    'feature_anion_count_3d': 'FeatureAnionCount3D',
    'feature_cation_count_3d': 'FeatureCationCount3D',
    'feature_ring_count_3d': 'FeatureRingCount3D',
    'feature_hydrophobe_count_3d': 'FeatureHydrophobeCount3D',
    'effective_rotor_count_3d': 'EffectiveRotorCount3D',
    'conformer_count_3d': 'ConformerCount3D',
}


def get_properties(properties, identifier, namespace='cid', searchtype=None, as_dataframe=False, **kwargs):
    if isinstance(properties, (str, bytes)):
        properties = properties.split(',')
    properties = ','.join([PROPERTY_MAP.get(p, p) for p in properties])
    properties = 'property/%s' % properties
    results = get_json(identifier, namespace, 'compound', properties, searchtype=searchtype, **kwargs)
    results = results['PropertyTable']['Properties'] if results else []
    if as_dataframe:
        import pandas as pd
        return pd.DataFrame.from_records(results, index='CID')
    return results


def get_synonyms(identifier, namespace='cid', domain='compound', searchtype=None, **kwargs):
    results = get_json(identifier, namespace, domain, 'synonyms', searchtype=searchtype, **kwargs)
    return results['InformationList']['Information'] if results else []


def get_cids(identifier, namespace='name', domain='compound', searchtype=None, **kwargs):
    results = get_json(identifier, namespace, domain, 'cids', searchtype=searchtype, **kwargs)
    if not results:
        return []
    elif 'IdentifierList' in results:
        return results['IdentifierList']['CID']
    elif 'InformationList' in results:
        return results['InformationList']['Information']


def get_sids(identifier, namespace='cid', domain='compound', searchtype=None, **kwargs):
    results = get_json(identifier, namespace, domain, 'sids', searchtype=searchtype, **kwargs)
    if not results:
        return []
    elif 'IdentifierList' in results:
        return results['IdentifierList']['SID']
    elif 'InformationList' in results:
        return results['InformationList']['Information']


def get_aids(identifier, namespace='cid', domain='compound', searchtype=None, **kwargs):
    results = get_json(identifier, namespace, domain, 'aids', searchtype=searchtype, **kwargs)
    if not results:
        return []
    elif 'IdentifierList' in results:
        return results['IdentifierList']['AID']
    elif 'InformationList' in results:
        return results['InformationList']['Information']


def get_all_sources(domain='substance'):
    """Return a list of all current depositors of substances or assays."""
    results = json.loads(get(domain, None, 'sources'))
    return results['InformationList']['SourceName']


def download(outformat, path, identifier, namespace='cid', domain='compound', operation=None, searchtype=None,
             overwrite=False, **kwargs):
    """Format can be  XML, ASNT/B, JSON, SDF, CSV, PNG, TXT."""
    response = get(identifier, namespace, domain, operation, outformat, searchtype, **kwargs)
    if not overwrite and os.path.isfile(path):
        raise IOError("%s already exists. Use 'overwrite=True' to overwrite it." % path)
    with open(path, 'w') as f:
        f.write(response)


def memoized_property(fget):
    """Decorator to create memoized properties.

    Used to cache :class:`~pubchempy.Compound` and :class:`~pubchempy.Substance` properties that require an additional
    request.
    """
    attr_name = '_{0}'.format(fget.__name__)
    @functools.wraps(fget)
    def fget_memoized(self):
        if not hasattr(self, attr_name):
            setattr(self, attr_name, fget(self))
        return getattr(self, attr_name)
    return property(fget_memoized)


class Compound(object):
    """Corresponds to a single record from the PubChem Compound database.

    The PubChem Compound database is constructed from the Substance database using a standardization and deduplication
    process.

    Each Compound is uniquely identified by a CID.
    """
    def __init__(self, record):
        self.record = record

    @classmethod
    def from_cid(cls, cid, **kwargs):
        """Retrieve the Compound record for the specified CID.

        :param cid: The PubChem Compound Identifier (CID).
        """
        record = json.loads(request(cid, **kwargs).decode())['PC_Compounds'][0]
        return cls(record)

    def __repr__(self):
        return 'Compound(%s)' % self.cid if self.cid else 'Compound()'

    def __eq__(self, other):
        return self.record == other.record

    def to_dict(self, properties=None):
        """Return a dictionary containing Compound data. Optionally specify a list of the desired properties.

        synonyms, aids and sids are not included unless explicitly specified using the properties parameter. This is
        because they each require an extra request.
        """
        if not properties:
            properties = [p for p in dir(Compound) if isinstance(getattr(Compound, p), property)]
        return {p: getattr(self, p) for p in properties}

    def to_series(self, properties=None):
        """Return a pandas :class:`~pandas.Series` containing Compound data. Optionally specify a list of the desired
        properties.

        synonyms, aids and sids are not included unless explicitly specified using the properties parameter. This is
        because they each require an extra request.
        """
        import pandas as pd
        return pd.Series(self.to_dict(properties))

    @property
    def cid(self):
        """The PubChem Compound Identifier (CID).

        .. note::

            When searching using a SMILES or InChI query that is not present in the PubChem Compound database, an
            automatically generated record may be returned that contains properties that have been calculated on the
            fly. These records will not have a CID property.
        """
        if 'id' in self.record and 'id' in self.record['id'] and 'cid' in self.record['id']['id']:
            return self.record['id']['id']['cid']

    @property
    def elements(self):
        return self.record['atoms']['element']

    @property
    def atoms(self):
        a = {
            'x': self.record['coords'][0]['conformers'][0]['x'],
            'y': self.record['coords'][0]['conformers'][0]['y'],
            'element': self.record['atoms']['element']
        }
        if 'z' in self.record['coords'][0]['conformers'][0]:
            a['z'] = self.record['coords'][0]['conformers'][0]['z']
        atomlist = list(map(dict, list(zip(*[[(k, v) for v in value] for k, value in a.items()]))))
        if 'charge' in self.record['atoms']:
            for charge in self.record['atoms']['charge']:
                atomlist[charge['aid']]['charge'] = charge['value']
        return atomlist

    @property
    def bonds(self):
        blist = list(map(dict, list(zip(*[[(k, v) for v in value] for k, value in self.record['bonds'].items()]))))
        if 'style' in self.record['coords'][0]['conformers'][0]:
            style = self.record['coords'][0]['conformers'][0]['style']
            for i, annotation in enumerate(style['annotation']):
                bond = [b for b in blist if all(aid in b.values() for aid in [style['aid1'][i], style['aid2'][i]])][0]
                bond['style'] = annotation
        return blist

    @memoized_property
    def synonyms(self):
        """A ranked list of all the names associated with this Compound.

        Requires an extra request. Result is cached.
        """
        if self.cid:
            results = get_json(self.cid, operation='synonyms')
            return results['InformationList']['Information'][0]['Synonym'] if results else []
            
    @memoized_property
    def sids(self):
        """Requires an extra request. Result is cached."""
        if self.cid:
            results = get_json(self.cid, operation='sids')
            return results['InformationList']['Information'][0]['SID'] if results else []

    @memoized_property
    def aids(self):
        """Requires an extra request. Result is cached."""
        if self.cid:
            results = get_json(self.cid, operation='aids')
            return results['InformationList']['Information'][0]['AID'] if results else []

    @property
    def coordinate_type(self):
        if 'twod' in self.record['coords'][0]['type']:
            return '2d'
        elif 'threed' in self.record['coords'][0]['type']:
            return '3d'

    @property
    def charge(self):
        if 'charge' in self.record:
            return self.record['charge']

    @property
    def molecular_formula(self):
        return _parse_prop({'label': 'Molecular Formula'}, self.record['props'])

    @property
    def molecular_weight(self):
        return _parse_prop({'label': 'Molecular Weight'}, self.record['props'])

    @property
    def canonical_smiles(self):
        return _parse_prop({'label': 'SMILES', 'name': 'Canonical'}, self.record['props'])

    @property
    def isomeric_smiles(self):
        return _parse_prop({'label': 'SMILES', 'name': 'Isomeric'}, self.record['props'])

    @property
    def inchi(self):
        return _parse_prop({'label': 'InChI', 'name': 'Standard'}, self.record['props'])

    @property
    def inchikey(self):
        return _parse_prop({'label': 'InChIKey', 'name': 'Standard'}, self.record['props'])

    @property
    def iupac_name(self):
        # Note: Allowed, CAS-like Style, Preferred, Systematic, Traditional are available in full record
        return _parse_prop({'label': 'IUPAC Name', 'name': 'Preferred'}, self.record['props'])

    @property
    def xlogp(self):
        return _parse_prop({'label': 'Log P'}, self.record['props'])

    @property
    def exact_mass(self):
        return _parse_prop({'label': 'Mass', 'name': 'Exact'}, self.record['props'])

    @property
    def monoisotopic_mass(self):
        return _parse_prop({'label': 'Weight', 'name': 'MonoIsotopic'}, self.record['props'])

    @property
    def tpsa(self):
        return _parse_prop({'implementation': 'E_TPSA'}, self.record['props'])

    @property
    def complexity(self):
        return _parse_prop({'implementation': 'E_COMPLEXITY'}, self.record['props'])

    @property
    def h_bond_donor_count(self):
        return _parse_prop({'implementation': 'E_NHDONORS'}, self.record['props'])

    @property
    def h_bond_acceptor_count(self):
        return _parse_prop({'implementation': 'E_NHACCEPTORS'}, self.record['props'])

    @property
    def rotatable_bond_count(self):
        return _parse_prop({'implementation': 'E_NROTBONDS'}, self.record['props'])

    @property
    def fingerprint(self):
        return _parse_prop({'implementation': 'E_SCREEN'}, self.record['props'])

    @property
    def heavy_atom_count(self):
        if 'count' in self.record and 'heavy_atom' in self.record['count']:
            return self.record['count']['heavy_atom']

    @property
    def isotope_atom_count(self):
        if 'count' in self.record and 'isotope_atom' in self.record['count']:
            return self.record['count']['isotope_atom']

    @property
    def atom_stereo_count(self):
        if 'count' in self.record and 'atom_chiral' in self.record['count']:
            return self.record['count']['atom_chiral']

    @property
    def defined_atom_stereo_count(self):
        if 'count' in self.record and 'atom_chiral_def' in self.record['count']:
            return self.record['count']['atom_chiral_def']

    @property
    def undefined_atom_stereo_count(self):
        if 'count' in self.record and 'atom_chiral_undef' in self.record['count']:
            return self.record['count']['atom_chiral_undef']

    @property
    def bond_stereo_count(self):
        if 'count' in self.record and 'bond_chiral' in self.record['count']:
            return self.record['count']['bond_chiral']

    @property
    def defined_bond_stereo_count(self):
        if 'count' in self.record and 'bond_chiral_def' in self.record['count']:
            return self.record['count']['bond_chiral_def']

    @property
    def undefined_bond_stereo_count(self):
        if 'count' in self.record and 'bond_chiral_undef' in self.record['count']:
            return self.record['count']['bond_chiral_undef']

    @property
    def covalent_unit_count(self):
        if 'count' in self.record and 'covalent_unit' in self.record['count']:
            return self.record['count']['covalent_unit']

    @property
    def volume_3d(self):
        conf = self.record['coords'][0]['conformers'][0]
        if 'data' in conf:
            return _parse_prop({'label': 'Shape', 'name': 'Volume'}, conf['data'])

    @property
    def multipoles_3d(self):
        conf = self.record['coords'][0]['conformers'][0]
        if 'data' in conf:
            return _parse_prop({'label': 'Shape', 'name': 'Multipoles'}, conf['data'])

    @property
    def conformer_rmsd_3d(self):
        coords = self.record['coords'][0]
        if 'data' in coords:
            return _parse_prop({'label': 'Conformer', 'name': 'RMSD'}, coords['data'])

    @property
    def effective_rotor_count_3d(self):
        return _parse_prop({'label': 'Count', 'name': 'Effective Rotor'}, self.record['props'])

    @property
    def pharmacophore_features_3d(self):
        return _parse_prop({'label': 'Features', 'name': 'Pharmacophore'}, self.record['props'])

    @property
    def mmff94_partial_charges_3d(self):
        return _parse_prop({'label': 'Charge', 'name': 'MMFF94 Partial'}, self.record['props'])

    @property
    def mmff94_energy_3d(self):
        conf = self.record['coords'][0]['conformers'][0]
        if 'data' in conf:
            return _parse_prop({'label': 'Energy', 'name': 'MMFF94 NoEstat'}, conf['data'])

    @property
    def conformer_id_3d(self):
        conf = self.record['coords'][0]['conformers'][0]
        if 'data' in conf:
            return _parse_prop({'label': 'Conformer', 'name': 'ID'}, conf['data'])

    @property
    def shape_selfoverlap_3d(self):
        conf = self.record['coords'][0]['conformers'][0]
        if 'data' in conf:
            return _parse_prop({'label': 'Shape', 'name': 'Self Overlap'}, conf['data'])

    @property
    def feature_selfoverlap_3d(self):
        conf = self.record['coords'][0]['conformers'][0]
        if 'data' in conf:
            return _parse_prop({'label': 'Feature', 'name': 'Self Overlap'}, conf['data'])

    @property
    def shape_fingerprint_3d(self):
        conf = self.record['coords'][0]['conformers'][0]
        if 'data' in conf:
            return _parse_prop({'label': 'Fingerprint', 'name': 'Shape'}, conf['data'])


def _parse_prop(search, proplist):
    """Extract property value from record using the given urn search filter."""
    props = [i for i in proplist if all(item in i['urn'].items() for item in search.items())]
    if len(props) > 0:
        return props[0]['value'][list(props[0]['value'].keys())[0]]


class Substance(object):
    """Corresponds to a single record from the PubChem Substance database.

    The PubChem Substance database contains all chemical records deposited in PubChem in their most raw form, before
    any significant processing is applied. As a result, it contains duplicates, mixtures, and some records that don't
    make chemical sense. This means that Substance records contain fewer calculated properties, however they do have
    additional information about the original source that deposited the record.

    The PubChem Compound database is constructed from the Substance database using a standardization and deduplication
    process. Hence each Compound may be derived from a number of different Substances.
    """

    @classmethod
    def from_sid(cls, sid):
        """Retrieve the Substance record for the specified SID.

        :param sid: The PubChem Substance Identifier (SID).
        """
        record = json.loads(request(sid, 'sid', 'substance'))['PC_Substances'][0]
        return cls(record)

    def __init__(self, record):
        self.record = record
        """A dictionary containing the full Substance record that all other properties are obtained from."""

    def __repr__(self):
        return 'Substance(%s)' % self.sid if self.sid else 'Substance()'

    def __eq__(self, other):
        return self.record == other.record

    def to_dict(self, properties=None):
        """Return a dictionary containing Substance data.

        If the properties parameter is not specified, everything except cids and aids is included. This is because the
        aids and cids properties each require an extra request to retrieve.

        :param properties: (optional) A list of the desired properties.
        """
        if not properties:
            properties = [p for p in dir(Substance) if isinstance(getattr(Substance, p), property) and
                                                       not p == 'deposited_compound']
        return {p: getattr(self, p) for p in properties}

    def to_series(self, properties=None):
        """Return a pandas :class:`~pandas.Series` containing Substance data.

        If the properties parameter is not specified, everything except cids and aids is included. This is because the
        aids and cids properties each require an extra request to retrieve.

        :param properties: (optional) A list of the desired properties.
        """
        import pandas as pd
        return pd.Series(self.to_dict(properties))

    @property
    def sid(self):
        """The PubChem Substance Idenfitier (SID)."""
        return self.record['sid']['id']

    @property
    def synonyms(self):
        """A ranked list of all the names associated with this Substance."""
        if 'synonyms' in self.record:
            return self.record['synonyms']

    @property
    def source_name(self):
        """The name of the PubChem depositor that was the source of this Substance."""
        return self.record['source']['db']['name']

    @property
    def source_id(self):
        """The ID of the PubChem depositor that was the source of this Substance."""
        return self.record['source']['db']['source_id']['str']

    @property
    def standardized_cid(self):
        """The CID of the Compound that was produced when this Substance was standardized.

        May not exist if this Substance was not standardizable.
        """
        for c in self.record['compound']:
            if c['id']['type'] == 'standardized':
                return c['id']['id']['cid']

    @memoized_property
    def standardized_compound(self):
        """Return the :class:`~pubchempy.Compound` that was produced when this Substance was standardized.

        Requires an extra request. Result is cached.
        """
        for c in self.record['compound']:
            if c['id']['type'] == 'standardized':
                return Compound.from_cid(c['id']['id']['cid'])

    @property
    def deposited_compound(self):
        """Return a :class:`~pubchempy.Compound` produced from the unstandardized Substance record as deposited.

        The resulting :class:`~pubchempy.Compound` will not have a cid and will be missing most properties.
        """
        for c in self.record['compound']:
            if c['id']['type'] == 'deposited':
                return Compound(c)

    @memoized_property
    def cids(self):
        """A list of all CIDs for Compounds that were produced when this Substance was standardized.

        Requires an extra request. Result is cached."""
        results = get_json(self.sid, 'sid', 'substance', 'cids')
        return results['InformationList']['Information'][0]['CID'] if results else []

    @memoized_property
    def aids(self):
        """A list of all AIDs for Assays associated with this Substance.

        Requires an extra request. Result is cached."""
        results = get_json(self.sid, 'sid', 'substance', 'aids')
        return results['InformationList']['Information'][0]['AID'] if results else []


class Assay(object):
    def __init__(self, record):
        self.record = record

    @classmethod
    def from_aid(cls, aid):
        record = json.loads(request(aid, 'aid', 'assay'))['PC_AssayContainer'][0]
        return cls(record)

    @property
    def aid(self):
        return self.record['id']['id']['aid']


def compounds_to_frame(compounds, properties=None):
    """Construct a pandas :class:`~pandas.DataFrame` from a list of :class:`~pubchempy.Compound` objects.

    Optionally specify a list of the desired :class:`~pubchempy.Compound` properties.
    """
    import pandas as pd
    if isinstance(compounds, Compound):
        compounds = [compounds]
    properties = set(properties) | set(['cid']) if properties else None
    return pd.DataFrame.from_records([c.to_dict(properties) for c in compounds], index='cid')


def substances_to_frame(substances, properties=None):
    """Construct a pandas :class:`~pandas.DataFrame` from a list of :class:`~pubchempy.Substance` objects.

    Optionally specify a list of the desired :class:`~pubchempy.Substance` properties.
    """
    import pandas as pd
    if isinstance(substances, Substance):
        substances = [substances]
    properties = set(properties) | set(['sid']) if properties else None
    return pd.DataFrame.from_records([s.to_dict(properties) for s in substances], index='sid')


# def add_columns_to_frame(dataframe, id_col, id_namespace, add_cols):
#     """"""
#     # Existing dataframe with some identifier column
#     # But consider what to do if the identifier column is an index?
#     # What about having the Compound/Substance object as a column?


class PubChemHTTPError(Exception):
    """Generic error class to handle all HTTP error codes."""
    def __init__(self, e):
        self.code = e.code
        self.msg = e.reason
        try:
            self.msg += ': %s' % json.load(e)['Fault']['Details'][0]
        except (ValueError, IndexError, KeyError):
            pass
        if self.code == 400:
            raise BadRequestError(self.msg)
        elif self.code == 404:
            raise NotFoundError(self.msg)
        elif self.code == 405:
            raise MethodNotAllowedError(self.msg)
        elif self.code == 504:
            raise TimeoutError(self.msg)
        elif self.code == 501:
            raise UnimplementedError(self.msg)
        elif self.code == 500:
            raise ServerError(self.msg)

    def __str__(self):
        return repr(self.msg)


class BadRequestError(PubChemHTTPError):
    """Request is improperly formed (syntax error in the URL, POST body, etc.)."""
    def __init__(self, msg='Request is improperly formed'):
        self.msg = msg


class NotFoundError(PubChemHTTPError):
    """The input record was not found (e.g. invalid CID)."""
    def __init__(self, msg='The input record was not found'):
        self.msg = msg


class MethodNotAllowedError(PubChemHTTPError):
    """Request not allowed (such as invalid MIME type in the HTTP Accept header)."""
    def __init__(self, msg='Request not allowed'):
        self.msg = msg


class TimeoutError(PubChemHTTPError):
    """The request timed out, from server overload or too broad a request.

    See :ref:`Avoiding TimeoutError <avoiding_timeouterror>` for more information.
    """
    def __init__(self, msg='The request timed out'):
        self.msg = msg


class UnimplementedError(PubChemHTTPError):
    """The requested operation has not (yet) been implemented by the server."""
    def __init__(self, msg='The requested operation has not been implemented'):
        self.msg = msg


class ServerError(PubChemHTTPError):
    """Some problem on the server side (such as a database server down, etc.)."""
    def __init__(self, msg='Some problem on the server side'):
        self.msg = msg


if __name__ == '__main__':
    print(__version__)
