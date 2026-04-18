import './tooltip.css';

export default function Tooltip({ text }) {
    return (
        <div className="tooltip-container">
            <div className="bg-main txt-other fs-md tooltip-icon">?</div>
            <div className="bg-base txt-base-on fs-sm tooltip-content">{text}</div>
        </div>
    );
}
