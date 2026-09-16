using System.ComponentModel.DataAnnotations;

namespace TrafficCounter.Api.Contracts.Inbound;
public sealed class ActivateCameraManagementRequest { [Required, StringLength(512)] public string Reason { get; set; } = ""; [Required, StringLength(128)] public string CameraId { get; set; } = ""; [Required, StringLength(128)] public string StreamProfileId { get; set; } = ""; }
public sealed class SelectManagedCameraRequest { [Required, StringLength(128)] public string CameraId { get; set; } = ""; [Required, StringLength(128)] public string StreamProfileId { get; set; } = ""; }
public sealed class UpdateCameraManagementDraftRequest { public int ExpectedRevision { get; set; } [Required] public Dictionary<string, double> Roi { get; set; } = []; [Required] public Dictionary<string, double> Line { get; set; } = []; }
