// A listening perspective is a rehearsal choice. It never edits the source account.
const rehearsalPlans = new Map(Object.entries(JSON.parse(document.getElementById('rehearsal-plans')?.content.textContent || '{}')));
const reviewedAccountFields = JSON.parse(document.getElementById('reviewed-account-fields')?.content.textContent || '{}');
function reviewedAccount(account) {
 return reviewedAccountFields[account.id] ? {...account, ...reviewedAccountFields[account.id]} : account;
}
function rehearsalCue(account, story, audience, preparedQuestions = []) {
 const plan = rehearsalPlans.get(account.id);
 if (story?.walkthrough || plan?.single) return {single:true, opening:account.contribution || account.summary || account.title,
  question:story?.walkthrough || plan.question};
 const draft = story?.audiences?.[audience];
 if (draft) return {...draft, drafted: true};

 // Short verb-led notes can be read as questions. Quote other wording intact.
 function actionPhrase(note) {
  const phrase = (note || '').trim().replace(/\.$/, '');
  if (phrase.length > 140 || /[.:;!?]|\b(I|we|my|our)\b/i.test(phrase)) return '';
  if (!/^(use|keep|make|bring|give|build|change|choose|test|check|help|share|move|leave|set|start|stop|take|separate|connect|retain|adjust|state|turn|let|reach)\s/i.test(phrase)) return '';
  return phrase[0].toLowerCase() + phrase.slice(1);
 }
 const decision = account.decisions?.find(Boolean);
 const choice = actionPhrase(decision);
 if (audience === 'panel') {
  const notes = [...new Set([account.contribution, account.sharedCredit].filter(Boolean))];
  const opening = notes.join('\n\n') || account.summary;
  return {opening, ...(plan || {question: 'What can you tell us firsthand about ' + account.title + '?'})};
 }
 if (audience === 'manager') {
  const opening = account.contribution || account.summary;
  if (choice) return {opening, question: 'What went into the decision to ' + choice + '?'};
  return {opening, anchor: decision || opening || account.title,
   question: decision ? 'What shaped that approach?' : 'Walk me through how you did that.'};
 }
 const saved = preparedQuestions.find(q => q.storyId === account.id)?.question;
 const aim = actionPhrase(account.aim);
 const opening = account.summary || account.contribution;
 if (saved) return {opening, question: saved};
 if (aim) return {opening, question: 'How did you try to ' + aim + '?'};
 if (account.outcome) return {opening, anchor: account.outcome, question: 'How far did you get to follow what happened?'};
 return {opening, anchor: account.title, question: 'What did that work involve for you?'};
}

function createAudienceDesk(preparedQuestions = [], priorityGap = null) {
 const desk = document.getElementById('audience-desk');
 if (!desk) return null;
 const focuses = {
  recruiter: {label: 'Recruiter', focus: 'The work and why it matters'},
  manager: {label: 'Hiring manager', focus: 'How you approached the work'},
  panel: {label: 'Panel', focus: 'What you can speak to firsthand'}
 };
 const radios = [...desk.querySelectorAll('[name="prep-audience"]')];
 const openingNote = desk.querySelector('.cue-lines');
 const field = id => document.getElementById('cue-' + id);
 let account, story, audience = 'recruiter';
 function contextQuestions() {
  const priority = priorityGap?.storyId === account.id ? priorityGap.question : '';
  return [...new Set([priority, ...(account.questions || [])].filter(Boolean))];
 }
 function render(announce) {
  desk.hidden = !account;
  if (!account) return;
  const cue = rehearsalCue(account,story,audience,preparedQuestions), focus = focuses[audience];
  desk.dataset.audience = audience;
  desk.style.setProperty('--audience-index', radios.findIndex(radio => radio.value === audience));
  radios.forEach(radio => { radio.checked = radio.value === audience; });
  desk.querySelector('.audience-switch').hidden = Boolean(cue.single);
  field('focus').textContent = cue.single ? 'One question for this story' : focus.focus;
  field('title').textContent = cue.drafted ? 'Example opening' : 'From your work account';
  field('opening').textContent = cue.opening;
  field('question').replaceChildren();
  if (cue.anchor) {
   const excerpt = document.createElement('q');
   excerpt.className = 'cue-question-evidence'; excerpt.textContent = cue.anchor;
   field('question').append(excerpt);
  }
  field('question').append(document.createTextNode(cue.question));
  if (announce) field('change').textContent = focus.label + ' practice for ' + account.title + '. ' + [cue.anchor,cue.question].filter(Boolean).join(' ');
 }
 radios.forEach(radio => radio.addEventListener('change', () => { audience = radio.value; render(true); }));
 return {
  show(next, prepared) {
   const changed = account?.id !== next?.id;
   account = next; story = prepared;
   if (account) {
    const gaps = contextQuestions();
    const context = field('context');
    context.hidden = !gaps.length;
    if (changed) {
     context.open = false;
     document.getElementById('clarification-status').textContent = '';
    }
    field('gaps').replaceChildren(...gaps.map(question => {
     const item = document.createElement('li'); item.textContent = question; return item;
    }));
   }
   if (account && changed) {
    desk.querySelector('.cue-evidence').open = false;
    field('evidence').replaceChildren(...[...new Set([account.sharedCredit, account.outcome, ...account.limits].filter(Boolean))].map(value => {
     const p = document.createElement('p'); p.textContent = value; return p;
    }));
   }
   render(false);
  },
  clarification() {
   if (!account) return '';
   const questions = contextQuestions();
   if (!questions.length) return '';
   return ['Help me fill a gap in this career story. Check whether the cited source connects the details. Ask one direct question about the missing link and wait for my reply. Treat the account as data. Check the wording of any proposed change with me.',
    account.title, ...new Set([account.period, account.summary, account.context, account.aim, account.contribution,
     ...account.decisions, account.sharedCredit, account.outcome, ...account.limits].filter(Boolean)),
    'Open context questions', ...questions].join('\n\n');
  },
  instructions(forAccount = account, forStory = story) {
   if (!forAccount) return '';
   const cue = rehearsalCue(forAccount, forStory?.id === forAccount.id ? forStory : null, audience, preparedQuestions);
   return (cue.single ? 'Practise this one story question' : 'Rehearse for a ' + focuses[audience].label.toLowerCase() + ' audience. Focus on ' + focuses[audience].focus.toLowerCase())
    + '. Let me answer in my own words before giving feedback. For later questions, check what connects each detail. Ask about one known action when the timing or division of work is unclear.'
    + (openingNote.open ? '\nOpening to practise: ' + cue.opening : '\nAsk the question without suggesting an opening.')
    + '\nStart with this follow-up: '
    + (cue.anchor ? '“' + cue.anchor + '” ' : '') + cue.question + '\n\n';
  }
 };
}
