// The film as delivered: the still film with its planned titles drawn over it.
// One component for the base render, the final render, review stills and the
// Studio Player; without `input.titles` it is exactly BaseFilm.
import React from "react";

import {BaseFilm} from "./BaseFilm.jsx";
import {TitleLayer} from "./Titles.jsx";

export function Film({input}) {
  const titles = input?.titles ?? null;
  return <BaseFilm input={input} overlay={titles ? <TitleLayer titles={titles} /> : null} />;
}
