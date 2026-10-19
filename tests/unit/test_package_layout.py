from ponto_eletronico import pipeline
from ponto_eletronico.extractors import henry_v1, henry_v2


def test_production_pipeline_and_extractors_are_importable():
    assert callable(pipeline.pipeline_principal)
    assert callable(henry_v1.automatizar_download_afd_v1)
    assert callable(henry_v2.automatizar_download_afd_v2)
