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
  n1lab: value => String(value || "").toLowerCase().includes("local") ? "Local" : "Autonómica",
  ccaaDe: value => value
};
vm.createContext(context);
vm.runInContext(["camino","anadirRutaPersonal","secuencia","mostrar","aplicaPerfil","estado","valorAid","evalAid","perfilNov","tiposBen","encajeNov","fuenteNov","estadoNov"].map(activeFunction).join("\n"), context);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(context.fuenteNov({id:"934562",link:"https://www.infosubvenciones.es/bdnstrans/GE/es/convocatoria/934562"}) === "Fuente: BDNS",
  "Las novedades BDNS deben mostrar su fuente aunque el registro antiguo no tenga el campo fuente.");
assert(context.fuenteNov({id:"cido-21573898",link:"https://cido.diba.cat/subvencions/21573898/ajuts"}) === "Fuente: CIDO · Diputació de Barcelona",
  "Las novedades CIDO deben conservar la atribución de origen.");
assert(context.fuenteNov({id:"UE-HORIZON-TEST",link:"https://ec.europa.eu/info/funding-tenders/topic-details/test"}) === "Fuente: Comisión Europea",
  "Las novedades de la UE deben identificar la fuente europea.");
assert(context.fuenteNov({id:"otro",organo:"Organismo local"}) === "Organismo: Organismo local · fuente por identificar",
  "No se debe inventar la fuente cuando no puede identificarse con seguridad.");
assert(context.estadoNov({}) === "por verificar" && context.estadoNov({estadoConvocatoria:"en plazo"}) === "en plazo" &&
  context.estadoNov({estadoConvocatoria:"cerrada"}) === "cerrada",
  "Las novedades sin estado confirmado deben quedar marcadas por verificar y conservar los estados conocidos.");
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
const localUnknownBeneficiary = context.encajeNov({
  n1:"local", n2:"Cataluña", n3:"Ajuntament de Barcelona",
  organo:"Ajuntament de Barcelona", titulo:"Ayuda local", beneficiarios:""
},pf);
assert(localUnknownBeneficiary.s === "mid",
  "Una novedad local sin beneficiarios identificados no debe descartarse si coincide con la residencia aunque la actividad esté en otra comunidad: " + JSON.stringify(localUnknownBeneficiary));

setAnswers({perfil:"particular",situacionPersonal:"familia",ccaa:"",municipio:"",ccaaResidencia:"Cataluña",provinciaResidencia:"Barcelona",municipioResidencia:"Barcelona"});
const pfParticular = context.perfilNov();
const personalOnlyRegional = context.encajeNov({
  n1:"regional", n2:"Cataluña", n3:"Generalitat de Catalunya",
  organo:"Generalitat de Catalunya", titulo:"Ayuda para familias",
  beneficiarios:"personas físicas y familias"
}, pfParticular);
const personalOnlyLocal = context.encajeNov({
  n1:"local", n2:"Cataluña", n3:"Ajuntament de Barcelona",
  organo:"Ajuntament de Barcelona", titulo:"Ayuda municipal para familias",
  beneficiarios:"personas físicas y familias"
}, pfParticular);
assert(personalOnlyRegional.s === "si" && personalOnlyLocal.s === "si",
  "El perfil particular debe evaluar las novedades autonómicas y locales con su residencia, aunque no tenga ubicación de actividad: " +
  JSON.stringify({pfParticular,personalOnlyRegional,personalOnlyLocal}));

setAnswers({perfil:"particular",situacionPersonal:"retorno",retorno:"si",cirbeNecesidad:"si"});
q = sequence();
assert(q.includes("trabajoExtranjero") && q.includes("cirbeNecesidad"),
  "La ruta de retorno debe ofrecer preguntas de trabajo exterior y necesidad de CIRBE.");
assert(context.mostrar("fechaRetorno"), "Debe mostrar la fecha de retorno si ya regresó.");

setAnswers({perfil:"particular",situacionPersonal:"familia",familia:"si",familiaEvento:"crianza"});
q = sequence();
assert(q.includes("familiaEvento") && q.includes("menores") && !q.includes("nacimientoFecha") && !q.includes("alquiler"),
  "La ruta de crianza debe preguntar por menores, sin pedir una fecha de nacimiento ni alquiler.");
setAnswers({perfil:"particular",situacionPersonal:"familia",familia:"si",familiaEvento:"primer_hijo"});
q = sequence();
assert(q.includes("nacimientoFecha") && !q.includes("menores"),
  "La ruta de primer hijo debe pedir la fecha, no un recuento de menores a cargo.");
setAnswers({perfil:"particular",situacionPersonal:"vivienda",alquiler:"si",nacionalidad:"espanola"});
q = sequence();
assert(q.indexOf("alquiler") < q.indexOf("contratoAlquiler") && q.indexOf("contratoAlquiler") < q.indexOf("empadronamiento"),
  "Las preguntas de alquiler deben aparecer antes de contrato y empadronamiento.");
assert(!context.mostrar("residenciaLegal"), "No debe pedir autorización de residencia a una persona con nacionalidad española.");
setAnswers({perfil:"particular",situacionPersonal:"retorno",retorno:"no",nacionalidad:"espanola"});
q = sequence();
assert(!q.includes("paisProcedencia") && !q.includes("cotizadosAntesEmigrar") && !q.includes("empleoSituacion"),
  "Si todavía no ha regresado, no debe mostrar el bloque de prestaciones posteriores al retorno.");
setAnswers({perfil:"particular",situacionPersonal:"retorno",retorno:"si",trabajoExtranjero:"si",nacionalidad:"espanola"});
q = sequence();
assert(q.includes("paisProcedencia") && q.includes("mesesTrabajoExtranjero") && q.includes("cotizadosAntesEmigrar"),
  "Tras confirmar el retorno y el trabajo en el extranjero, deben aparecer las preguntas necesarias para SEPE.");
setAnswers({perfil:"particular",situacionPersonal:"desempleo",edad:"53"});
q = sequence();
assert(q.includes("cotizacionDesempleo6"), "La pregunta de seis años cotizados solo debe aparecer al llegar a los 52 años.");
setAnswers({perfil:"particular",situacionPersonal:"desempleo",social:"si",familia:"si",alquiler:"si"});
const familyAidWrongRoute = context.evalAid({perfil:"personal",reqs:{familia:"si"}});
const housingAidWrongRoute = context.evalAid({perfil:"personal",reqs:{alquiler:"si"}});
assert(familyAidWrongRoute.s === "no" && housingAidWrongRoute.s === "no",
  "Las ayudas de familia y alquiler deben descartarse cuando la persona ha elegido otra ruta.");
setAnswers({perfil:"particular",situacionPersonal:"familia",familia:"si",familiaEvento:"crianza"});
const birthAidWrongEvent = context.evalAid({perfil:"personal",reqs:{familia:"si",familiaEvento:{oneOf:["primer_hijo","otro_hijo"]}}});
assert(birthAidWrongEvent.s === "no", "Una ayuda por nacimiento no debe encajar automáticamente si solo busca ayudas de crianza.");

setAnswers({perfil:"particular",situacionPersonal:"desempleo",cotizados:"300",empleoSituacion:"asalariado",motivoFin:"despido"});
const insufficientDays = context.evalAid({perfil:"personal",reqs:{situacionPersonal:"desempleo",cotizados:{min:360}}});
assert(insufficientDays.s === "no", "La evaluación numérica debe descartar cotizaciones inferiores al mínimo requerido.");
setAnswers({perfil:"particular",situacionPersonal:"desempleo",cotizados:"420",empleoSituacion:"asalariado",motivoFin:"baja_voluntaria"});
const voluntaryQuit = context.evalAid({perfil:"personal",reqs:{motivoFin:{oneOf:["despido","fin_contrato","ere","otro"]}}});
assert(voluntaryQuit.s === "no", "La evaluación por opciones debe descartar la baja voluntaria cuando el requisito es desempleo legal.");

setAnswers({perfil:"autonomo",alta:"si"});
assert(context.aplicaPerfil({perfil:"negocio"}) && !context.aplicaPerfil({perfil:"personal"}),
  "El perfil autónomo debe priorizar ayudas de actividad; las ayudas personales se incluyen al elegir el perfil mixto.");
q = sequence();
assert(q.includes("plantilla") && q.includes("direccionIgual"),
  "La ruta de autónomo debe conservar las preguntas de actividad y preguntar si la dirección fiscal coincide.");
assert(!q.includes("situacionPersonal") && !q.includes("social") && !q.includes("fiscal") && !q.includes("emergencias"),
  "La ruta de autónomo no debe repetir el cuestionario personal.");
setAnswers({perfil:"autonomo",alta:"si",direccionIgual:"si",ccaa:"Cataluña",municipio:"Lleida"});
q = sequence();
assert(!q.includes("ccaaResidencia") && !q.includes("provinciaResidencia") && !q.includes("municipioResidencia"),
  "Si las direcciones coinciden, no debe pedir una segunda ubicación.");
setAnswers({perfil:"autonomo",alta:"si",direccionIgual:"no"});
q = sequence();
assert(q.includes("ccaaResidencia") && q.includes("provinciaResidencia") && q.includes("municipioResidencia"),
  "Si las direcciones son distintas, debe pedir la ubicación de residencia.");
setAnswers({perfil:"ambos",alta:"si",direccionIgual:"si"});
q = sequence();
assert(q.includes("situacionPersonal") && q.includes("social") && !q.includes("ccaaResidencia"),
  "El perfil mixto mantiene la ruta personal, pero reutiliza la dirección del negocio si coincide.");

const status = context.estado({pend:true,cierre:"2020-01-01",plazo:"Fecha provisional"});
assert(status.k === "pending", "Una convocatoria pendiente no debe cerrarse por una fecha provisional ya pasada.");
const ongoing = context.estado({perm:true,estadoManual:"Requisitos sujetos a comprobación oficial"});
assert(ongoing.k === "perm", "Una prestación de solicitud continua no debe etiquetarse como pendiente de convocatoria.");

console.log("OK: rutas de particulares, desempleo, familia, perfil mixto, autónomo y estado pendiente.");
