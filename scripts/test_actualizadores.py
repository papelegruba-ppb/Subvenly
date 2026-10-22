#!/usr/bin/env python3
"""Pruebas de regresión locales para los importadores de Subvenly. No usan red."""
import datetime as dt
import sys
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import actualizar
import actualizar_licitaciones


class TestCoberturaBDNS(unittest.TestCase):
    def test_incluye_ayudas_personales_y_sectoriales(self):
        casos = [
            {"descripcion": "Becas para estudios universitarios 2026"},
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
