import type { LookSection } from "../api";

/** One palette and one light per section, as wide as the section is long. */
export function ColourScript({ sections }: { sections: LookSection[] }) {
  if (!sections.length) return null;
  return (
    <div className="profile-list">
      <b className="profile-label">Colour by section</b>
      <div className="colour-script">
        {sections.map((section) => (
          <div
            className="colour-script-part"
            key={section.id}
            style={{ flexGrow: section.end - section.start }}
            title={`${section.light}${section.lens ? `, ${section.lens}` : ""}`}
          >
            <div className="colour-script-swatches">
              {section.palette.map((colour) => (
                <span
                  key={colour}
                  // A palette may be words a browser cannot draw; those stay as text.
                  style={CSS.supports("color", colour) ? { background: colour } : undefined}
                  title={colour}
                >
                  {CSS.supports("color", colour) ? "" : colour}
                </span>
              ))}
            </div>
            <small>{section.id}</small>
          </div>
        ))}
      </div>
    </div>
  );
}
