

// Carrega o XML das câmeras
function ExibirImgCamera(element) {
    setarCameraId(element.value);

    var id = element.value;
    var texto = '';

    $.ajax({
        type: "GET",
        url: FileCamXML,
        async: false,
        dataType: "xml",
        error: function () {
            alert("Erro ao ler as câmeras");
        },
        success: function (xml) {
            $(xml).find('CameraXML').each(function () {
                var j_cod = $(this).find('id').text();
                var j_rod = $(this).find('rodovia').text();
                var j_den = $(this).find('localizacao').text();
                var j_cam = $(this).find('municipio').text();
                var j_loc = $(this).find('km').text();
                //var j_img = $(this).find('image').text();
                var j_sen = $(this).find('sentido').text();
                var j_atv = $(this).find('ativo').text();
                var j_mtv = $(this).find('motivo').text();
                var cam_der = $(this).find('cam_der').text();
                var isVideo = $(this).find('isVideo').text();
                var videoLink = $(this).find('videoLink').text();

                if (cam_der == "True") {
                    cam_der = "DER";
                } else {
                    cam_der = "Contratada";
                }

                var dt = new Date();
                var d = dt.getTime();

                if (id == j_cod) {
                    if (j_atv == 'True') {
                        if (isVideo == 'True') {
                            if (videoLink.includes('.m3u8')) {
                                texto += '<video id="video-' + j_cod + '" width="550" height="350" autoplay muted playsinline style="pointer-events: none;"></video>';
                            } else {
                                texto += '<video width="550" height="350" autoplay muted playsinline style="pointer-events: none;">';
                                texto += '<source src="' + videoLink + '?' + d + '" type="video/mp4">';
                                texto += 'Seu navegador não suporta o elemento de vídeo.';
                                texto += '</video>';
                            }
                        } else {
                            texto += '<img src="' + url_cameras + j_img + '?' + d + '" id="img_camera" class="img-thumbnail" />';
                        }
                    } else {
                        switch (j_mtv) {
                            case '1':
                                texto += '<img src="' + url_cameras_status + 'cam_indisponivel.png" id="img_camera" class="img-thumbnail" />';
                                break;
                            case '3':
                                texto += '<img src="' + url_cameras_status + 'cam_indisponivel_telefonia.png" id="img_camera" class="img-thumbnail" />';
                                break;
                            case '2':
                                texto += '<img src="' + url_cameras_status + 'cam_indisponivel_energia.png" id="img_camera" class="img-thumbnail" />';
                                break;
                            case '4':
                                texto += '<img src="' + url_cameras_status + 'cam_indisponivel.png" id="img_camera" class="img-thumbnail" />';
                                break;
                        }
                    }

                    texto += '<br><p style="text-align:left; color: black; cursor: default">';
                    texto += '<br><b>Rodovia: </b>' + j_rod + ' - ' + 'km: ' + j_loc + ' - ' + j_den;
                    texto += '<br><b>Câmera: </b>' + j_cam;
                    texto += '<br><b>Sentido: </b>' + j_sen;
                    texto += '<br><b>Administração: </b>' + cam_der;
                    texto += '</p>';
                }
            });

            $('#ConteudoCamera').show();
            $('#ConteudoCamera').html(texto);

            $(xml).find('CameraXML').each(function () {
                var j_cod = $(this).find('id').text();
                var isVideo = $(this).find('isVideo').text();
                var videoLink = $(this).find('videoLink').text();

                if (id == j_cod && isVideo == 'True' && videoLink.includes('.m3u8')) {
                    var video = document.getElementById('video-' + j_cod);
                    if (Hls.isSupported()) {
                        var hls = new Hls();
                        hls.loadSource(videoLink);
                        hls.attachMedia(video);
                    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
                        video.src = videoLink;
                    }
                }
            });

            GAnalitycs();
            ContadorCamMap();
        }
    });
}


function setarCameraId(id) {
    let url = new URL(window.location);
    url.searchParams.set("camera", id);
    window.history.pushState({}, "", url);
}
function ExibirImgCameraId(id) {
    setarCameraId(id);

    var texto = '';

    $.ajax({
        type: "GET",
        url: FileCamXML,
        async: false,
        dataType: "xml",
        error: function () {
            alert("Erro ao ler as câmeras");
        },
        success: function (xml) {
            $(xml).find('CameraXML').each(function () {
                var j_cod = $(this).find('id').text();
                var j_rod = $(this).find('rodovia').text();
                var j_den = $(this).find('localizacao').text();
                var j_cam = $(this).find('municipio').text();
                var j_loc = $(this).find('km').text();
                var j_img = $(this).find('image').text();
                var j_sen = $(this).find('sentido').text();
                var j_atv = $(this).find('ativo').text();
                var j_mtv = $(this).find('motivo').text();
                var cam_der = $(this).find('cam_der').text();
                var isVideo = $(this).find('isVideo').text();
                var videoLink = $(this).find('videoLink').text();

                if (cam_der == "True") {
                    cam_der = "DER";
                } else {
                    cam_der = "Contratada";
                }

                var dt = new Date();
                var d = dt.getTime();

                if (id == j_cod) {
                    if (j_atv == 'True') {
                        if (isVideo == 'True') {
                            if (videoLink.includes('.m3u8')) {
                                texto += '<video id="video-' + j_cod + '" width="550" height="350" autoplay muted playsinline style="pointer-events: none;"></video>';
                            } else {
                                texto += '<video width="550" height="350" autoplay muted playsinline style="pointer-events: none;">';
                                texto += '<source src="' + videoLink + '?' + d + '" type="video/mp4">';
                                texto += 'Seu navegador não suporta o elemento de vídeo.';
                                texto += '</video>';
                            }
                        } else {
                            texto += '<img src="' + url_cameras + j_img + '?' + d + '" id="img_camera" class="img-thumbnail" />';
                        }
                    } else {
                        switch (j_mtv) {
                            case '1':
                                texto += '<img src="' + url_cameras_status + 'cam_indisponivel.png" id="img_camera" class="img-thumbnail" />';
                                break;
                            case '3':
                                texto += '<img src="' + url_cameras_status + 'cam_indisponivel_telefonia.png" id="img_camera" class="img-thumbnail" />';
                                break;
                            case '2':
                                texto += '<img src="' + url_cameras_status + 'cam_indisponivel_energia.png" id="img_camera" class="img-thumbnail" />';
                                break;
                            case '4':
                                texto += '<img src="' + url_cameras_status + 'cam_indisponivel.png" id="img_camera" class="img-thumbnail" />';
                                break;
                        }
                    }

                    texto += '<br><p style="text-align:left; color: black; cursor: default">';
                    texto += '<br><b>Rodovia: </b>' + j_rod + ' - ' + 'km: ' + j_loc + ' - ' + j_den;
                    texto += '<br><b>Câmera: </b>' + j_cam;
                    texto += '<br><b>Sentido: </b>' + j_sen;
                    texto += '<br><b>Administração: </b>' + cam_der;
                    texto += '</p>';
                }
            });

            $('#ConteudoCamera').show();
            $('#ConteudoCamera').html(texto);

            $(xml).find('CameraXML').each(function () {
                var j_cod = $(this).find('id').text();
                var isVideo = $(this).find('isVideo').text();
                var videoLink = $(this).find('videoLink').text();

                if (id == j_cod && isVideo == 'True' && videoLink.includes('.m3u8')) {
                    var video = document.getElementById('video-' + j_cod);
                    if (Hls.isSupported()) {
                        var hls = new Hls();
                        hls.loadSource(videoLink);
                        hls.attachMedia(video);
                    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
                        video.src = videoLink;
                    }
                }
            });

            GAnalitycs();
            ContadorCamMap();
        }
    });
}







//function AtualizarImagem() {
//    var camera = $("#img_camera").attr('src');
//    var nomecam = camera.split("?");
//    $("#img_camera").attr('src', nomecam[0] + "?" + (new Date()).getTime());
//}


function MCamShow_New() {
    var texto = '';
    var txt = '<select class="form-control" style="height:40px;" name="lstCam" id="lstCam" onchange="ExibirImgCameraId($(\'#lstCam\').val())";>';
    txt += '<option value="0">SELECIONE UMA C�?MERA</option>';
    var ListaCam = '/Upload/XML/cameras.xml';
    $.ajax({
        type: "GET",
        url: FileCamXML,
        async: false,
        dataType: "xml",
        error: function () { alert("Erro de processamento nas Cameras"); },
        success: function (xml) {
            $(xml).find('CameraXML').each(function () {
                var id = $(this).find('id').text();
                var rodovia = $(this).find('rodovia').text();
                var localizacao = $(this).find('localizacao').text();
                var municipio = $(this).find('municipio').text();
                var sentido = $(this).find('sentido').text();
                var km = $(this).find('km').text();
                var cam_der = $(this).find('cam_der').text();

                if (cam_der === "True") {
                    txt += '<option value="' + id + '">' + rodovia + ' - km ' + km + ' - ' + municipio + ' >> ' + sentido + '</option>';
                }

            });
            txt += '</select>';
            $('#ListaCam').html(txt);
            $('#ConteudoCamera').show();
            $('#ConteudoCamera').html(texto);
        }
    });

}

function MCamShow() {

    var iDer = 0;
    var iContratada = 0;
    var iTotal = 0;
    $.ajax({
        url: FileCamXML,
        dataType: "xml",
        success: function (xmlResponse) {
            var data = $("CameraXML", xmlResponse).map(function () {
                var txt = "";
                var id = $(this).find('id').text();
                var rodovia = $(this).find('rodovia').text();
                var localizacao = $(this).find('localizacao').text();
                var municipio = $(this).find('municipio').text();
                var sentido = $(this).find('sentido').text();
                var km = $(this).find('km').text();
                var cam_der = $(this).find('cam_der').text();
                var cam_derB = $(this).find('cam_der').text();
                // iTotal = iTotal +1;


                if (cam_der == "True") {
                    cam_der = " (DER) ";
                    iDer = iDer + 1;
                } else {
                    cam_der = " (Contratada) ";
                    iContratada = iContratada + 1;
                }
                iTotal = iTotal + 1;
                txt = rodovia + ' - km ' + km + ' - ' + localizacao + ' - ' + municipio + ' >> ' + sentido; // cam_der;
                return { value: txt, id: id };



            }).get();

            var dataOrdenada = data.slice(0);
            dataOrdenada.sort(function (a, b) {
                var x = a.value.toLowerCase();
                var y = b.value.toLowerCase();
                return x < y ? -1 : x > y ? 1 : 0;
            });

            var txt = '';
            for (x = 0; x < dataOrdenada.length; x++) {
                txt += '<option value="' + dataOrdenada[x].id + '">' + dataOrdenada[x].value + '</option>';
            }
            $("#sRodovia").append(txt);

            $("#iTotal").html(iTotal);
            $("#iDer").html(iDer);
            $("#iContratada").html(iContratada);
            $("#sRodovia").trigger("chosen:updated");
            selecionarCameraFromUrl();
            //$('#sRodovia').searchableOptionList({
            //    maxHeight: '250px',
            //    events: {
            //        onChange: function (sol, changedElements) {
            //            ExibirImgCamera(changedElements.context);
            //        }
            //    }
            //});
        }
    });

}
function selecionarCameraFromUrl() {
    const urlParams = new URLSearchParams(window.location.search);

    if (urlParams.has("camera")) {
        if (document.querySelector("#sRodovia").options.length > 0) {
            for (let x = 0; x < document.querySelector("#sRodovia").options.length; x++) {
                let cam = urlParams.get("camera");
                console.log("selecionado")
                if (document.querySelector("#sRodovia").options[x].value == cam) {
                    document.querySelector("#sRodovia").selectedIndex = x;
                    document.querySelector("#sRodovia").dispatchEvent(new Event('change'));
                    break;
                }
            }
        }
    }
}
function GAnalitycs() {
    var _gaq = _gaq || [];
    _gaq.push(['_setAccount', 'UA-31606204-1']);
    _gaq.push(['_trackPageview']);
    (function () {
        var ga = document.createElement('script'); ga.type = 'text/javascript'; ga.async = true;
        ga.src = ('https:' == document.location.protocol ? 'https://ssl' : 'http://www') + '.google-analytics.com/ga.js';
        var s = document.getElementsByTagName('script')[0]; s.parentNode.insertBefore(ga, s);
    })();
}

function ContadorCamMap() {
    //$('#IframeContador').html(contar);
    var ContaCamMap = '<iframe src="/WebSite/Servicos/ServicosOnline/ContaCamMap.aspx" scrolling="no" width="1" height="1" frameborder="1" style="display:none"></iframe>';
    $('#IframeContador').append(ContaCamMap);
}
function ContadorCamLista() {
    //$('#IframeContador').html(contar);
    var ContaCamLista = '<iframe src="/WebSite/Servicos/ServicosOnline/ContaCamLista.aspx" scrolling="no" width="1" height="1" frameborder="1" style="display:none"></iframe>';
    $('#IframeContador').append(ContaCamLista);
}


$(document).ready(function () {
    MCamShow()
});
