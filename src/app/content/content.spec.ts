import { PORTFOLIO_EN } from './portfolio.en';
import { PORTFOLIO_ES } from './portfolio.es';
import { UI_EN } from './ui.en';
import { UI_ES } from './ui.es';

describe('portfolio content', () => {
  it('lists the same jobs and projects in both languages', () => {
    expect(PORTFOLIO_ES.experience.map((e) => e.id)).toEqual(PORTFOLIO_EN.experience.map((e) => e.id));
    expect(PORTFOLIO_ES.projects.map((p) => p.slug)).toEqual(PORTFOLIO_EN.projects.map((p) => p.slug));
  });

  it('translates every summary and project tagline', () => {
    PORTFOLIO_ES.experience.forEach((job, i) => expect(job.summary).not.toBe(PORTFOLIO_EN.experience[i].summary));
    PORTFOLIO_ES.projects.forEach((project, i) => expect(project.tagline).not.toBe(PORTFOLIO_EN.projects[i].tagline));
  });

  it('keeps one build phase name per job in Terra', () => {
    expect(UI_EN.terra.phases.length).toBe(PORTFOLIO_EN.experience.length);
    expect(UI_ES.terra.phases.length).toBe(PORTFOLIO_ES.experience.length);
  });

  it('avoids the em dash in the Spanish copy', () => {
    expect(JSON.stringify(PORTFOLIO_ES)).not.toContain('—');
    expect(JSON.stringify(UI_ES)).not.toContain('—');
  });
});
