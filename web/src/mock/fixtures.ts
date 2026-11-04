/**
 * Canned data for the mock agent. Titles, authors and figures are PLACEHOLDERS, not real WRI
 * publications (as in the AskWRI design system's wireframes). Delete with the rest of src/mock/.
 */

import type { Source } from "../lib/agent.ts";

// shortcut: placeholder links point at WRI's research listing, so "Open at page" lands on wri.org
const WRI_RESEARCH = "https://www.wri.org/research";

export const SOURCES: Source[] = [
  {
    marker: 1,
    chunkId: "mock-ebus-transition#p12-1",
    docId: "mock-ebus-transition",
    title: "Electric bus transition in Latin American cities",
    pubType: "Report",
    year: 2019,
    dateConfidence: "high",
    office: "WRI México",
    page: 12,
    pageCount: 64,
    passage: "fleet operators in three cities piloted battery-electric buses on existing routes",
    quotable: true,
    url: WRI_RESEARCH,
    doi: null,
    authors: ["Author A", "Author B"],
  },
  {
    marker: 2,
    chunkId: "mock-financing-zero-emission#p4-2",
    docId: "mock-financing-zero-emission",
    title: "Financing zero-emission bus fleets",
    pubType: "Working paper",
    year: 2021,
    dateConfidence: "high",
    office: "WRI Brasil",
    page: 4,
    pageCount: 38,
    passage: "lease models separated vehicle ownership from operations, lowering the upfront cost for operators",
    quotable: true,
    url: WRI_RESEARCH,
    doi: "10.46830/mock.21.00001",
    authors: ["Author C"],
  },
  {
    marker: 3,
    chunkId: "mock-transport-emissions#p31-1",
    docId: "mock-transport-emissions",
    title: "Urban transport emissions baseline",
    pubType: "Technical note",
    year: 2008,
    dateConfidence: "high",
    office: "Ross Center",
    page: 31,
    pageCount: 48,
    passage: "diesel buses accounted for a large share of urban transport emissions",
    quotable: true,
    url: WRI_RESEARCH,
    doi: null,
    authors: ["Author D"],
  },
  {
    marker: 4,
    chunkId: "mock-procurement-reforms#p2-1",
    docId: "mock-procurement-reforms",
    title: "Lessons from bus procurement reforms",
    pubType: "Issue brief",
    year: 2022,
    dateConfidence: "high",
    office: "Ross Center",
    page: 2,
    pageCount: 12,
    passage: "procurement rules were updated to allow total-cost-of-ownership bids",
    quotable: true,
    url: WRI_RESEARCH,
    doi: "10.46830/mock.22.00002",
    authors: ["Author B", "Author E"],
  },
  {
    marker: 5,
    chunkId: "mock-ebus-costs-updated#p3-1",
    docId: "mock-ebus-costs-updated",
    title: "Zero-emission bus costs: updated estimates",
    pubType: "Issue brief",
    year: 2022,
    dateConfidence: "high",
    office: "WRI Brasil",
    page: 3,
    pageCount: 10,
    passage: "updated estimates put the cost gap at about half of the 2019 figure",
    quotable: true,
    url: WRI_RESEARCH,
    doi: null,
    authors: ["Author C", "Author F"],
  },
  {
    marker: 6,
    chunkId: "mock-brt-planning#p18-2",
    docId: "mock-brt-planning",
    title: "Bus rapid transit planning in Latin America",
    pubType: "Guidebook",
    year: 2006,
    dateConfidence: "low",
    office: "WRI (global)",
    page: 18,
    pageCount: 120,
    passage: "early BRT systems replaced diesel fleets on trunk corridors first",
    quotable: false, // diagram labels: cite the page, never quote
    url: null,
    doi: null,
    authors: ["Author G"],
  },
];

export const QUICK_PARAGRAPHS = {
  en: [
    "WRI has published on bus electrification in Latin America across reports, working papers and briefs [1][2][4]. Pilots showed that operators could run battery-electric buses on existing routes [1]. Lease models that separated vehicle ownership from operations lowered the upfront cost [2].",
    "Older work set the baseline: diesel buses were a large share of urban transport emissions [3]. More recent briefs focus on procurement rules that score total cost of ownership [4].",
  ],
  es: [
    "WRI ha publicado sobre la electrificación de autobuses en América Latina en informes, documentos de trabajo y notas [1][2][4]. Los proyectos piloto mostraron que los operadores podían usar autobuses eléctricos de batería en las rutas existentes [1]. Los modelos de arrendamiento que separaron la propiedad de los vehículos de la operación redujeron el costo inicial [2].",
    "Trabajos anteriores fijaron la línea de base: los autobuses diésel eran una gran parte de las emisiones del transporte urbano [3]. Las notas más recientes se centran en reglas de compra que valoran el costo total de propiedad [4].",
  ],
};

export const REPORT_POINTS = {
  en: [
    "Pilots in several cities showed operators could run battery-electric buses on existing routes [1].",
    "Separating vehicle ownership from operations lowered upfront cost [2].",
    "Updated estimates put the remaining cost gap at about half of the 2019 figure; use the newer number [5][1].",
    "Procurement rules that score total cost of ownership help electric bids compete [4].",
    "Early bus rapid transit corridors are where diesel fleets were replaced first [6][3].",
  ],
  es: [
    "Proyectos piloto en varias ciudades mostraron que los operadores podían usar autobuses eléctricos de batería en las rutas existentes [1].",
    "Separar la propiedad de los vehículos de la operación redujo el costo inicial [2].",
    "Las estimaciones actualizadas sitúan la brecha de costos restante en cerca de la mitad de la cifra de 2019; use la cifra más reciente [5][1].",
    "Las reglas de compra que valoran el costo total de propiedad ayudan a que las ofertas eléctricas compitan [4].",
    "Los primeros corredores de autobuses de tránsito rápido son donde primero se reemplazaron las flotas diésel [6][3].",
  ],
};

export const THIN_EVIDENCE = {
  en: [
    "No publication in this collection covers end-of-life battery handling for buses in Latin America.",
    "Only one document covers Central America; most evidence is from Brazil and Mexico.",
    "Based on the sampled collection, not WRI's full library.",
  ],
  es: [
    "Ninguna publicación de esta colección trata el manejo de baterías al final de su vida útil para autobuses en América Latina.",
    "Solo un documento cubre Centroamérica; la mayor parte de la evidencia es de Brasil y México.",
    "Basado en la colección de muestra, no en toda la biblioteca de WRI.",
  ],
};

export const SUB_QUESTIONS = "pilots, financing, procurement, emissions baseline";
