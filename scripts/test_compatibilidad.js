#!/usr/bin/env node
"use strict";
const fs = require("node:fs");
const vm = require("node:vm");
const html = fs.readFileSync("index.html", "utf8");

function activeFunction(name) {
  const start = html.lastIndexOf("function " + name + "(");
  if (start < 0) throw new Error("No se encuentra la función activa " + name);
  const end = html.indexOf("\nfunction ", start + 1);
  return html.slice(start, end < 0 ? html.length : end);
}
function assertEqual(actual, expected, label) {
  if (actual !== expected) throw new Error(label + ": esperado " + expected + ", recibido " + actual);
}
const values = {};
const context = {
  values,
  valorAid: key => values[key],
  nrm: value => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase(),
  n1lab: value => {
    const t = String(value || "").toLowerCase();
    return t.includes("union europea") || t === "ue" ? "Unión Europea" :
      t.startsWith("estatal") ? "Estatal" : t.includes("autonom") || t === "regional" ? "Autonómica" :
      t.includes("local") ? "Local" : "Otros";
  },
  ccaaDe: value => String(value || ""),
  tiposBen: value => value && typeof value === "object" ? value : null
};
vm.createContext(context);
vm.runInContext([activeFunction("evalAid"), activeFunction("encajeNov")].join("\n"), context);

function testAid(label, answerValues, aid, expected) {
  Object.keys(values).forEach(k => delete values[k]);
  Object.assign(values, answerValues);
  assertEqual(context.evalAid(aid).s, expected, label);
}
testAid("1. Requisitos exactos", {alta:"si",ccaa:"Cataluña"}, {reqs:{alta:"si",ccaa:"Cataluña"}}, "si");
testAid("2. Requisito incumplido", {alta:"no"}, {reqs:{alta:"si"}}, "no");
testAid("3. Respuesta ausente", {}, {reqs:{alta:"si"}}, "mid");
testAid("4. Respuesta No sé", {alta:"nose"}, {reqs:{alta:"si"}}, "mid");
testAid("5. Opción permitida", {familiaEvento:"primer_hijo"}, {reqs:{familiaEvento:{oneOf:["primer_hijo","otro_hijo"]}}}, "si");
testAid("6. Opción excluida", {familiaEvento:"crianza"}, {reqs:{familiaEvento:{oneOf:["primer_hijo","otro_hijo"]}}}, "no");
testAid("7. Valor numérico dentro del mínimo", {cotizados:"420"}, {reqs:{cotizados:{min:360}}}, "si");
testAid("8. Valor numérico inferior al mínimo", {cotizados:"300"}, {reqs:{cotizados:{min:360}}}, "no");
testAid("9. Ficha sin requisitos evaluables", {}, {reqs:{}}, "mid");
testAid("10. Ficha pendiente de verificación", {alta:"si"}, {reqs:{alta:"si"},pend:true}, "mid");

function profile(overrides={}) {
  return Object.assign({perfil:"particular",particular:true,aut:false,soc:false,ccaa:"Cataluña",muni:"Barcelona",ccaaResidencia:"Cataluña",muniResidencia:"Barcelona"}, overrides);
}
function novelty(label, item, pf, expected) {
  const result = context.encajeNov(item, pf);
  assertEqual(result.s, expected, label + (result.why.length ? " (" + result.why.join("; ") + ")" : ""));
}
const persona = {persona:true,aut:false,soc:false};
const empresa = {persona:false,aut:true,soc:true};
novelty("11. Ayuda autonómica en la comunidad correcta",
  {n1:"Autonómica",n2:"Cataluña",beneficiarios:persona}, profile(), "si");
novelty("12. Ayuda autonómica fuera de la comunidad",
  {n1:"Autonómica",n2:"Galicia",beneficiarios:persona}, profile(), "no");
novelty("13. Territorio autonómico sin datos suficientes",
  {n1:"Autonómica",n2:"",beneficiarios:persona}, profile({ccaa:""}), "mid");
novelty("14. Ayuda local en el municipio correcto",
  {n1:"Local",n2:"Cataluña",n3:"Ajuntament de Barcelona",titulo:"Ayuda municipal",organo:"Ajuntament de Barcelona",beneficiarios:persona},
  profile(), "si");
novelty("15. Ayuda local en municipio distinto",
  {n1:"Local",n2:"Cataluña",n3:"Ajuntament de Girona",titulo:"Ayuda municipal",organo:"Ajuntament de Girona",beneficiarios:persona},
  profile(), "no");
novelty("16. Beneficiarios no identificados",
  {n1:"Autonómica",n2:"Cataluña",beneficiarios:""}, profile(), "mid");
novelty("17. Ayuda estatal: no excluir por comunidad autónoma",
  {n1:"Estatal",n2:"España",beneficiarios:empresa}, profile({perfil:"autonomo",particular:false,aut:true,soc:false}), "si");
novelty("18. Ayuda empresarial para perfil particular",
  {n1:"Estatal",n2:"España",beneficiarios:empresa}, profile(), "no");
novelty("19. Ayuda europea con beneficiarios compatibles",
  {n1:"Unión Europea",n2:"Unión Europea",beneficiarios:persona}, profile(), "si");
novelty("20. Ayuda europea sin beneficiarios identificados",
  {n1:"Unión Europea",n2:"Unión Europea",beneficiarios:""}, profile(), "mid");

console.log("OK: 20 pruebas de compatibilidad (10 evalAid y 10 encajeNov).");
