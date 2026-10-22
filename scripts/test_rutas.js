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

const context = {
  A: {},
  DEP: {indefinido:"contratar", joven:"contratar", bcn:"contratar", sl24:"sl"},
  CATONLY: ["amb", "lleida", "centre", "ponent"],
  IMPLICITO: {sl:{nuevo:"no",tarifa:"no",jovenyo:"no",paro:"no",desempleado:"no"},aut:{sl:"no",sl24:"no"}},
  fmt: value => value,
  Date,
  Math,
  Array,
  nrm: value => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase(),
  eff: key => context.A[key],
  n1lab: () => "Autonómica",
  ccaaDe: n => n.n2
};
vm.createContext(context);
vm.runInContext(["camino","secuencia","mostrar","estado","valorAid","evalAid","perfilNov","tiposBen","encajeNov"].map(activeFunction).join("\n"), context);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
function setAnswers(values) { context.A = values; }
function sequence() { return Array.from(context.secuencia()); }

setAnswers({perfil:"particular",situacionPersonal:"desempleo",familia:"si",social:"si",ccaa:"Cataluña",provincia:"Barcelona",paroPrevio:"si",demandaEmpleo:"no"});
let q = sequence();
assert(q.includes("situacionPersonal") && q.includes("empleoSituacion") && q.includes("cotizados") && q.includes("tramitar"),
  "La ruta de desempleo no incluye las preguntas específicas.");
assert(context.mostrar("fechaAgotamiento"), "Debe pedir fecha de agotamiento cuando se confirma paro previo.");
context.A.paroPrevio = "no";
assert(!context.mostrar("fechaAgotamiento"), "No debe pedir fecha de agotamiento si no se agotó el paro.");
context.A.paroPrevio = "si";
assert(!context.mostrar("fechaRetorno"), "No debe mostrar la fecha de retorno en la ruta de desempleo.");

setAnswers({perfil:"particular",situacionPersonal:"familia",familia:"si"});
q = sequence();
assert(q.includes("familiaEvento") && !q.includes("empleoSituacion"),
  "La ruta familiar debe evitar preguntas de desempleo.");
assert(!context.mostrar("empleoSituacion"), "No debe mostrar preguntas de empleo en la ruta familiar.");

setAnswers({perfil:"ambos",situacionPersonal:"desempleo",familia:"si"});
q = sequence();
assert(q.includes("alta") && q.includes("ccaa") && q.includes("situacionPersonal") && q.includes("empleoSituacion"),
  "El perfil mixto debe conservar la ruta de negocio y mostrar la ruta personal aunque falte forma jurídica.");

setAnswers({perfil:"ambos",ccaa:"Comunidad de Madrid",provincia:"Madrid",municipio:"Madrid",ccaaResidencia:"Cataluña",provinciaResidencia:"Barcelona",municipioResidencia:"Barcelona"});
q = sequence();
assert(q.includes("ccaa") && q.includes("ccaaResidencia") && q.includes("municipioResidencia"),
  "El perfil mixto debe recoger por separado la ubicación de actividad y la residencia.");
const personalAid = context.evalAid({perfil:"personal",reqs:{ccaa:"Cataluña"}});
const businessAid = context.evalAid({perfil:"negocio",reqs:{ccaa:"Comunidad de Madrid"}});
assert(personalAid.s === "si" && businessAid.s === "si",
  "Las ayudas personales deben evaluarse con la residencia y las empresariales con el centro de actividad.");

setAnswers({perfil:"ambos",alta:"si",ccaa:"Comunidad de Madrid",provincia:"Madrid",municipio:"Madrid",ccaaResidencia:"Cataluña",provinciaResidencia:"Barcelona",municipioResidencia:"Barcelona"});
const pf = context.perfilNov();
const personalNovelty = context.encajeNov({n1:"regional",n2:"Cataluña",beneficiarios:"personas físicas y familias"},pf);
const businessNovelty = context.encajeNov({n1:"regional",n2:"Comunidad de Madrid",beneficiarios:"autónomos y pymes"},pf);
assert(personalNovelty.s === "si" && businessNovelty.s === "si",
  "Las novedades personales y empresariales deben comparar su territorio correspondiente: " + JSON.stringify({pf,personalNovelty,businessNovelty}));

setAnswers({perfil:"particular",situacionPersonal:"retorno",retorno:"si",cirbeNecesidad:"si"});
q = sequence();
assert(q.includes("trabajoExtranjero") && q.includes("cirbeNecesidad"),
  "La ruta de retorno debe ofrecer preguntas de trabajo exterior y necesidad de CIRBE.");
assert(context.mostrar("fechaRetorno"), "Debe mostrar la fecha de retorno si ya regresó.");

setAnswers({perfil:"autonomo",alta:"si",situacionPersonal:"ingresos"});
q = sequence();
assert(q.includes("plantilla") && q.includes("social") && q.includes("ingresosPersonales"),
  "La ruta de autónomo debe mantener las preguntas de empresa y ayudas personales.");

const status = context.estado({pend:true,cierre:"2020-01-01",plazo:"Fecha provisional"});
assert(status.k === "pending", "Una convocatoria pendiente no debe cerrarse por una fecha provisional ya pasada.");

console.log("OK: rutas de particulares, desempleo, familia, perfil mixto, autónomo y estado pendiente.");
