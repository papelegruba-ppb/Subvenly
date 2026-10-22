#!/usr/bin/env python3
"""Pruebas de regresión locales para los importadores de Subvenly. No usan red."""
import datetime as dt
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import actualizar
import actualizar_licitaciones
import actualizar_ue
import actualizar_cido
import vigilar_fuentes
import hashlib


class TestCoberturaBDNS(unittest.TestCase):
    def test_incluye_ayudas_personales_y_sectoriales(self):
        casos = [
            {"descripcion": "Becas para estudios universitarios 2026"},
            {"descripcion": "Subvención nominativa para una asociación local"},
            {"descripcion": "Ayuda extraordinaria para gastos de sepelio"},
            {"descripcion": "Subvención para clubes deportivos de base"},
            {"descripcion": "Ayudas a la modernización de explotaciones ganaderas"},
            {"descripcion": "Programa de accesibilidad y cuidados a personas mayores"},
            {"descripcion": "Subvenciones para rehabilitación energética de viviendas"},
        ]
        for caso in casos:
            with self.subTest(titulo=caso["descripcion"]):
                self.assertTrue(actualizar.relevante(caso))

    def test_excluye_titulos_sin_terminos_de_ayuda(self):
        self.assertFalse(actualizar.relevante({"descripcion": "Anuncio de una reunión ordinaria"}))

    def test_busca_tambien_en_titulo_cooficial(self):
        self.assertTrue(actualizar.relevante({
            "descripcion": "Convocatoria general de subvenciones",
            "descripcionLeng": "Ajuts per a la investigació agrícola",
        }))

    def test_detalle_normaliza_plazo_y_beneficiarios(self):
        raw = {
            "fechaInicioSolicitud": "2026-10-01",
            "fechaFinSolicitud": "2026-10-29",
            "tiposBeneficiarios": [{"descripcion": "Empresas y profesionales"}],
            "presupuestoTotal": 100000,
            "urlBasesReguladoras": "https://example.test/bases.pdf",
            "sedeElectronica": "https://example.test/solicitud",
        }
        result = actualizar.campos_detalle(raw)
        self.assertEqual(result["plazo_inicio"], "2026-10-01")
        self.assertEqual(result["plazo_fin"], "2026-10-29")
        self.assertEqual(result["beneficiarios"], "Empresas y profesionales")


class TestCIDO(unittest.TestCase):
    def fixture_rss(self):
        return """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel>
          <item>
            <title>Ajuts per a la digitalització de negocis locals 2026</title>
            <link>https://cido.diba.cat/subvencions/21573898/ajuts-digitals</link>
            <guid>https://cido.diba.cat/subvencions/21573898/ajuts-digitals</guid>
            <pubDate>Wed, 21 Oct 2026 18:02:51 +0200</pubDate>
            <description><![CDATA[Data de publicació: 21/10/2026 18:02:51 Ens: Ajuntament de Lleida Número de referència: 20261021S1]]></description>
          </item>
          <item>
            <title>Ajuts socials per a famílies 2026</title>
            <link>https://cido.diba.cat/subvencions/21573899/ajuts-socials</link>
            <pubDate>Thu, 22 Oct 2026 09:00:00 +0200</pubDate>
            <description><![CDATA[Ens: Ajuntament de Balaguer Número de referència: 20261022S2]]></description>
          </item>
        </channel></rss>""".encode("utf-8")

    def test_parsea_rss_como_descubrimiento_no_confirmacion_de_plazo(self):
        items = actualizar_cido.parsear_rss(self.fixture_rss(), dt.date(2026, 10, 22))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["id"], "cido-21573898")
        self.assertEqual(items[0]["n1"], "Local")
        self.assertEqual(items[0]["n2"], "Cataluña")
        self.assertEqual(items[0]["organo"], "Ajuntament de Lleida")
        self.assertEqual(items[0]["fecha"], "2026-10-21")
        self.assertEqual(items[0]["estadoConvocatoria"], "por verificar")
        self.assertTrue(items[0]["link"].startswith("https://cido.diba.cat/subvencions/"))

    def test_clasifica_el_feed_de_becas_segun_el_organismo(self):
        xml = self.fixture_rss().replace(b"Ajuntament de Lleida", b"Generalitat de Catalunya")
        items = actualizar_cido.parsear_rss(
            xml, dt.date(2026, 10, 22),
            feed="https://cido.diba.cat/rss/subvencions/beques",
            nivel_defecto="Otros",
        )
        self.assertEqual(items[0]["n1"], "Autonómica")
        self.assertEqual(items[0]["n2"], "Cataluña")
        self.assertEqual(items[0]["categoriaFuente"], "becas")
        self.assertEqual(items[0]["estadoConvocatoria"], "por verificar")

    def test_merge_preserva_bdns_y_deduplica_cido(self):
        nuevos = actualizar_cido.parsear_rss(self.fixture_rss(), dt.date(2026, 10, 22))
        previo = {"actualizado":"2026-10-21", "items":[
            {"id":"12345","titulo":"BDNS existente","fecha":"2026-10-21","visto":"2026-10-21"},
            {"id":"cido-21573898","titulo":"Versión anterior","fecha":"2026-10-20","visto":"2026-10-20"}
        ]}
        combinado, resumen = actualizar_cido.combinar(previo, nuevos, dt.date(2026, 10, 22))
        ids = [x["id"] for x in combinado["items"]]
        self.assertEqual(ids.count("cido-21573898"), 1)
        self.assertIn("12345", ids)
        actualizado = next(x for x in combinado["items"] if x["id"] == "cido-21573898")
        self.assertEqual(actualizado["titulo"], "Ajuts per a la digitalització de negocis locals 2026")
        self.assertEqual(actualizado["visto"], "2026-10-20")
        self.assertEqual(resumen["nuevas"], 1)

    def test_bdns_no_consulta_el_endpoint_de_detalle_para_cido(self):
        self.assertTrue(actualizar.es_bdns({"id":"123456"}))
        self.assertFalse(actualizar.es_bdns({"id":"cido-123456","fuente":"CIDO"}))
        self.assertFalse(actualizar.es_bdns({"id":"ABC-123"}))


class TestVigilanciaFuentes(unittest.TestCase):
    def test_detecta_cambios_sin_red(self):
        fuente = {"id":"fuente-prueba","url":"https://example.test/ayudas"}
        anterior = {"fuente-prueba":{"estado":"igual","hash":hashlib.sha256(b"antes").hexdigest(),
                                     "texto":"antes","cambios":[],"url":fuente["url"]}}
        with patch.object(vigilar_fuentes, "permitido", return_value=True), patch.object(vigilar_fuentes, "obtener", return_value="después"):
            sid, actual, mensaje = vigilar_fuentes.procesar_fuente(fuente, anterior, "2026-10-22")
        self.assertEqual(sid, "fuente-prueba")
        self.assertEqual(actual["estado"], "cambio")
        self.assertEqual(actual["cambios"][0]["antes"], "antes")
        self.assertIn("cambio", mensaje)

    def test_mantiene_aviso_hasta_revision(self):
        texto = "contenido"
        huella = hashlib.sha256(texto.encode("utf-8")).hexdigest()
        fuente = {"id":"fuente-prueba","url":"https://example.test/ayudas"}
        anterior = {"fuente-prueba":{"estado":"cambio","hash":huella,"texto":texto,"cambios":[{"fecha":"2026-10-21"}]}}
        with patch.object(vigilar_fuentes, "permitido", return_value=True), patch.object(vigilar_fuentes, "obtener", return_value=texto):
            _, actual, _ = vigilar_fuentes.procesar_fuente(fuente, anterior, "2026-10-22")
        self.assertEqual(actual["estado"], "cambio")
        self.assertEqual(len(actual["cambios"]), 1)


class TestConvocatoriasUE(unittest.TestCase):
    def test_error_temporal_de_consulta_ue_no_aborta_el_importador(self):
        with patch.object(actualizar_ue.urllib.request, "urlopen", side_effect=TimeoutError("timeout")):
            anterior = actualizar_ue.ERRORES_CONSULTA
            actualizar_ue.ERRORES_CONSULTA = 0
            try:
                self.assertIsNone(actualizar_ue.consultar("SME", 0))
                self.assertEqual(actualizar_ue.ERRORES_CONSULTA, 1)
            finally:
                actualizar_ue.ERRORES_CONSULTA = anterior

    def test_separa_fecha_detectada_apertura_y_estado(self):
        raw = {
            "metadata": {
                "identifier": ["HORIZON-TEST-01"],
                "title": ["Open call for small businesses"],
                "startDate": ["2027-02-01T00:00:00.000+0000"],
                "deadlineDate": ["2027-05-30T00:00:00.000+0000"],
                "status": ["31094501"],
            },
            "url": "https://example.test/topic",
        }
        item = actualizar_ue.convertir(raw, dt.date(2026, 10, 22))
        self.assertEqual(item["fecha"], "2026-10-22")
        self.assertEqual(item["fechaTipo"], "detectada")
        self.assertEqual(item["plazo_inicio"], "2027-02-01")
        self.assertEqual(item["plazo_fin"], "2027-05-30")
        self.assertEqual(item["estadoConvocatoria"], "próxima")


class TestLicitaciones(unittest.TestCase):
    def make_entry(self, status="PUB", deadline="2026-11-16"):
        xml = f'''<entry xmlns="http://www.w3.org/2005/Atom">
          <id>urn:uuid:test-123</id><updated>2026-10-20</updated>
          <title>Servicio de prueba</title><link href="https://example.test/licitacion"/>
          <ContractFolderID>EXP-123</ContractFolderID>
          <ContractFolderStatusCode>{status}</ContractFolderStatusCode>
          <ProcurementProject>
            <Name>Servicio de prueba</Name><TypeCode>2</TypeCode>
            <RealizedLocation><CountrySubentity>Badajoz</CountrySubentity><CountrySubentityCode>ES431</CountrySubentityCode></RealizedLocation>
            <BudgetAmount><TaxExclusiveAmount>1000</TaxExclusiveAmount></BudgetAmount>
            <RequiredCommodityClassification><ItemClassificationCode>55330000</ItemClassificationCode></RequiredCommodityClassification>
          </ProcurementProject>
          <LocatedContractingParty><PartyName><Name>Órgano de prueba</Name></PartyName></LocatedContractingParty>
          <TenderSubmissionDeadlinePeriod><EndDate>{deadline}</EndDate></TenderSubmissionDeadlinePeriod>
        </entry>'''
        return ET.fromstring(xml)

    def test_parsea_licitacion_publicada_en_plazo(self):
        item = actualizar_licitaciones.entrada(self.make_entry(), dt.date(2026, 10, 22))
        self.assertIsNotNone(item)
        self.assertEqual(item["id"], "EXP-123")
        self.assertEqual(item["cierre"], "2026-11-16")
        self.assertEqual(item["presupuesto"], 1000)
        self.assertEqual(item["link"], "https://example.test/licitacion")

    def test_excluye_licitacion_no_publicada_o_vencida(self):
        hoy = dt.date(2026, 10, 22)
        self.assertIsNone(actualizar_licitaciones.entrada(self.make_entry(status="PRE"), hoy))
        self.assertIsNone(actualizar_licitaciones.entrada(self.make_entry(deadline="2026-10-01"), hoy))

    def test_recorrer_fixture_atom_sin_red(self):
        entry = ET.tostring(self.make_entry(), encoding="utf-8")
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom">' + entry + b'</feed>'
        rows, pages, next_url, complete = actualizar_licitaciones.recorrer("fixture", "2026-10-01", dt.date(2026, 10, 22), raiz_local=atom)
        self.assertEqual(pages, 1)
        self.assertEqual(next_url, "")
        self.assertTrue(complete)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "EXP-123")

    def test_recorrer_guarda_cursor_si_alcanza_limite_de_paginas(self):
        atom = '''<feed xmlns="http://www.w3.org/2005/Atom">
          <entry><id>urn:uuid:test</id><updated>2026-10-20</updated>
            <title>Servicio de prueba</title><link href="https://example.test/licitacion"/>
            <ContractFolderID>EXP-123</ContractFolderID><ContractFolderStatusCode>PUB</ContractFolderStatusCode>
            <ProcurementProject><Name>Servicio de prueba</Name><TypeCode>2</TypeCode>
              <RealizedLocation><CountrySubentity>Badajoz</CountrySubentity><CountrySubentityCode>ES431</CountrySubentityCode></RealizedLocation>
              <BudgetAmount><TaxExclusiveAmount>1000</TaxExclusiveAmount></BudgetAmount>
            </ProcurementProject>
            <LocatedContractingParty><PartyName><Name>Órgano de prueba</Name></PartyName></LocatedContractingParty>
            <TenderSubmissionDeadlinePeriod><EndDate>2026-11-16</EndDate></TenderSubmissionDeadlinePeriod>
          </entry>
          <link rel="next" href="https://example.test/page2"/>
        </feed>'''.encode("utf-8")
        with patch.object(actualizar_licitaciones, "MAX_FICHEROS", 1), patch.object(actualizar_licitaciones, "leer_url", return_value=atom):
            rows, pages, next_url, complete = actualizar_licitaciones.recorrer("https://example.test/page1", "2026-10-01", dt.date(2026, 10, 22))
        self.assertEqual(pages, 1)
        self.assertEqual(next_url, "https://example.test/page2")
        self.assertFalse(complete)
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
