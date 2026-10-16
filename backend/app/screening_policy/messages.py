from app.domain import Outcome

DISCLAIMER = ("This AI-assisted screening is not a medical diagnosis. A photograph cannot reliably determine the complete "
              "severity of a diabetic foot ulcer or rule out infection. If you suspect an ulcer or notice concerning "
              "symptoms, seek assessment from a qualified healthcare professional.")

OUTCOME_TEXT: dict[Outcome, dict] = {
    Outcome.no_obvious_wound: {
        "title": "No obvious wound identified in the photograph",
        "summary": "This does not rule out an ulcer, infection or other foot problem. A photograph can miss things.",
        "next_steps": ["Keep checking your feet every day.", "See a healthcare professional if you notice any change."]},
    Outcome.possible_superficial_wound: {
        "title": "Possible superficial wound",
        "summary": "The app cannot confirm the clinical stage of a wound. Professional assessment may be required.",
        "next_steps": ["Have the area assessed by a doctor or podiatrist.", "Keep pressure off the area and keep it clean and protected."]},
    Outcome.possible_deeper_wound: {
        "title": "Possible deeper wound or concerning findings",
        "summary": "The photo may show something more serious than this app can evaluate. This is not a diagnosis.",
        "next_steps": ["Arrange assessment by a doctor or podiatrist soon.",
                       "Therapeutic slippers are not presented as suitable based on this result."]},
    Outcome.inconclusive_image: {
        "title": "Inconclusive: the photos could not be assessed",
        "summary": "This is NOT a normal result. The photos were unclear, incomplete or could not be analysed.",
        "next_steps": ["Retake the photos in good, even light.", "If you have symptoms, do not wait: contact a healthcare professional."]},
    Outcome.clinical_review_required: {
        "title": "Clinical review required",
        "summary": "Your answers or photos need review by a qualified clinician before any footwear is offered.",
        "next_steps": ["A clinician review is needed before purchase.", "Contact your doctor if symptoms change."]},
    Outcome.urgent_warning: {
        "title": "Urgent: please get medical assessment",
        "summary": "The symptoms you reported can be signs of a serious foot problem, including infection. This app cannot assess that.",
        "next_steps": ["Contact your doctor or diabetes care team today, or go to the nearest hospital if you feel unwell or have fever.",
                       "Do not wait for an app result or an online order.", "Footwear purchase is paused."]},
}

TRIAGE_GUIDANCE = {
    "urgent": "Your answers include warning signs that can mean a serious problem. Please seek urgent medical assessment before continuing.",
    "caution": "Some answers need extra care. You can continue, but a clinician review may be needed before footwear is offered.",
    "routine": "",
}
