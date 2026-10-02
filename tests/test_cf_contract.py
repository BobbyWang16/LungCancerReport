"""Current CF taxonomy, coverage, conflicts and model/resource consistency."""
import copy,json
from pathlib import Path
import pytest
from app.features import CATEGORIES,prompt_dictionary
from app.multihorizon_risk import validate_multihorizon,score_multihorizon
from test_full_cohort_model import synthetic

@pytest.fixture
def bundle():return json.loads((Path(__file__).resolve().parents[1]/'models/active_model.json').read_text(encoding='utf8'))

def test_category_semantics_match_export_and_prompt(bundle):
    assert bundle['histology_codebook']=={str(k):v for k,v in CATEGORIES['histology_code'].items()}
    assert CATEGORIES['histology_code'][6]=='ASC' and CATEGORIES['histology_code'][7]=='MIX'
    hist=next(x for x in prompt_dictionary('PATH') if x['field']=='histology_code')
    assert hist['categories']==CATEGORIES['histology_code']
    bad=copy.deepcopy(bundle);bad['histology_codebook']['1']='LUSC'
    with pytest.raises(ValueError,match='字典'):validate_multihorizon(bad)

def test_current_priorities_are_public_and_separate_from_coefficients(bundle):
    from app.multihorizon_risk import public_multihorizon
    public=public_multihorizon(bundle)
    assert public['feature_importance']['version']==bundle['version']
    rows=public['feature_importance']['prognostic_validation']
    assert rows and all('mean_delta_brier' in r for r in rows)
    assert 'coefficients' not in public

@pytest.mark.parametrize('mod',[None,'CE','NCE','PET_CT'])
def test_review_and_missing_data_block(bundle,mod):
    fs=synthetic(bundle,mod)
    for f in fs:
        if f['key']!='PATH.histology_code':f.update(value=None,status='missing')
    assert score_multihorizon(fs,True,bundle)['status']=='unavailable'
    fs=synthetic(bundle,mod);next(f for f in fs if f['key']=='PATH.histology_code').update(status='conflict',value=-6)
    assert score_multihorizon(fs,True,bundle)['status']=='unavailable'

@pytest.mark.parametrize('code',range(1,13))
def test_each_histology_respects_frozen_gates(bundle,code):
    for mod in [None,'CE','NCE','PET_CT']:
        r=score_multihorizon(synthetic(bundle,mod,code),True,bundle)
        if r['status']=='available':
            model=bundle['models'][r['selected_model']]
            for y,out in r['risks_by_year'].items():
                if out['status']=='available':
                    assert model['horizons'][y]['research_enabled']
                    assert model['histology_support'][CATEGORIES['histology_code'][code]][y]['enabled']
        if CATEGORIES['histology_code'][code] not in bundle['site_model']['supported_histologies']:assert not r['top_sites']
