from pydantic import BaseModel


class ManualStep(BaseModel):
    step_number: int
    title: str
    action_type: str  # click / input / scroll / navigate / other
    target_element: str
    description: str
    expected_result: str
    screenshot_filename: str


class ManualStructure(BaseModel):
    title: str
    overview: str
    target_application: str
    prerequisites: list[str]
    steps: list[ManualStep]


class GenerateRequest(BaseModel):
    video_filename: str


class GenerateResponse(BaseModel):
    status: str
    manual_id: str
    manual_html_url: str
    manual_json: ManualStructure
